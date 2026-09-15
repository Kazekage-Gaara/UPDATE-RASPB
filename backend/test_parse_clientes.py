import os
import tempfile
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import Cliente, Gateway, Unidad
from parsers import parse_clientes


class ParseClientesUnitAssociationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.original_session = parse_clientes.SessionLocal
        parse_clientes.SessionLocal = self.Session

    def tearDown(self):
        parse_clientes.SessionLocal = self.original_session
        self.engine.dispose()

    def _parse(self, content):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as preset:
            preset.write(content)
            path = preset.name
        try:
            parse_clientes.parse_clientes_file(path, "cana")
        finally:
            os.unlink(path)

    def test_direct_gateway_lines_create_distinct_units_and_migrate_legacy_unit(self):
        with self.Session() as db:
            cliente = Cliente(nombre="Alcoolvale", tipo_cultivo="cana", subred="210.99.0.0")
            db.add(cliente)
            db.flush()
            legacy = Unidad(ip="210.99.1.5", nombre="Vivencia 1", cliente_id=cliente.id)
            db.add(legacy)
            db.flush()
            db.add_all([
                Gateway(ip="210.99.1.105", unidad_id=legacy.id, cliente_id=cliente.id),
                Gateway(ip="210.99.1.115", unidad_id=legacy.id, cliente_id=cliente.id),
            ])
            db.commit()

        self._parse("""210.99.0.0/24 Alcoolvale
1.105 Vivencia 1 user : one
1.115 Vivencia 2 user : two
1.125 Vivencia 3 user : three
""")

        with self.Session() as db:
            units = {unit.ip: unit.nombre for unit in db.query(Unidad).all()}
            self.assertEqual(units, {
                "210.99.1.105": "Vivencia 1",
                "210.99.1.115": "Vivencia 2",
                "210.99.1.125": "Vivencia 3",
            })
            gateway = db.query(Gateway).filter_by(ip="210.99.1.115").one()
            self.assertEqual(gateway.unidad.nombre, "Vivencia 2")

    def test_base_unit_keeps_all_of_its_gateways_together(self):
        self._parse("""220.10.0.0/24 Cliente
1.5 Fazenda Principal
.105 Torre sede
.115 Torre norte
""")

        with self.Session() as db:
            units = [(unit.ip, unit.nombre) for unit in db.query(Unidad).all()]
            self.assertEqual(units, [("220.10.1.5", "Fazenda Principal")])
            cliente = db.query(Cliente).one()
            db.add(Gateway(ip="220.10.1.115", cliente_id=cliente.id))
            db.commit()
            parse_clientes.reasociar_gateways_importados(db)
            db.commit()
            gateway = db.query(Gateway).one()
            self.assertEqual(gateway.unidad.nombre, "Fazenda Principal")


if __name__ == "__main__":
    unittest.main()
