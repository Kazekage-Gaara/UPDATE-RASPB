from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Float, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base

class Cliente(Base):
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    tipo_cultivo = Column(String, nullable=False)
    subred = Column(String, nullable=False, unique=True)
    ip_mikrotik = Column(String, nullable=True)
    notas = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    gateways = relationship("Gateway", back_populates="cliente")
    unidades = relationship("Unidad", back_populates="cliente")

class Unidad(Base):
    __tablename__ = "unidades"
    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String, unique=True, index=True, nullable=False)
    nombre = Column(String, nullable=False)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    cliente = relationship("Cliente", back_populates="unidades")

class Gateway(Base):
    __tablename__ = "gateways"
    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String, unique=True, index=True, nullable=False)
    version = Column(String, nullable=True)
    status = Column(String, nullable=True)
    last_scan = Column(DateTime(timezone=True), server_default=func.now())
    last_update = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    
    # Relaciones
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True, index=True)
    unidad_id = Column(Integer, ForeignKey("unidades.id"), nullable=True, index=True)
    cliente = relationship("Cliente", back_populates="gateways")
    unidad = relationship("Unidad")
    
    # 🆕 NUEVOS CAMPOS - Datos del SolinfNet.conf
    description = Column(String, nullable=True)  # "TORRE SEDE", "Faz. Perpetua", etc.
    fleet_number = Column(String, nullable=True)  # Server_GroupNumber: 313000
    latitude = Column(Float, nullable=True)  # Coordenadas GPS
    longitude = Column(Float, nullable=True)
    vid = Column(String, nullable=True)  # VID: 0329
    hardware_type = Column(String, nullable=True)  # Hardware: Local, Relay, RadioLocal
    use_gps = Column(Boolean, nullable=True)  # UseGPS: 1/0
    
    # 🆕 NUEVO CAMPO - Versión del Sistema Operativo
    os_version = Column(String, nullable=True)  # "Debian 8", "Debian 9", "Debian 10", etc.
    os_codename = Column(String, nullable=True)  # "jessie", "stretch", "buster", etc.
    
    # 🆕 NUEVO CAMPO - Relay LPWAN
    has_relay = Column(Boolean, nullable=True)  # True si tiene bloque Hardware=Relay

class UpdateHistory(Base):
    __tablename__ = "update_history"
    id = Column(Integer, primary_key=True, index=True)
    gateway_ip = Column(String, index=True, nullable=False)
    old_version = Column(String, nullable=True)
    new_version = Column(String, nullable=True)
    status = Column(String, nullable=False)
    duration_seconds = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class GatewayDiagnosticEvent(Base):
    __tablename__ = "gateway_diagnostic_events"
    id = Column(Integer, primary_key=True, index=True)
    gateway_ip = Column(String, index=True, nullable=False)
    event_type = Column(String, index=True, nullable=False)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
