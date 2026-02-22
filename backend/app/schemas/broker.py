"""Pydantic schemas for broker connection."""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum


class BrokerType(str, Enum):
    ZERODHA = "zerodha"
    FYERS = "fyers"
    ANGELONE = "angelone"
    UPSTOX = "upstox"
    GROWW = "groww"


class BrokerConnectRequest(BaseModel):
    broker: BrokerType
    api_key: str
    api_secret: Optional[str] = None
    client_id: Optional[str] = None
    # For token-based auth (e.g., Zerodha request_token after OAuth)
    request_token: Optional[str] = None
    # For TOTP-based auth (e.g., AngelOne)
    totp_secret: Optional[str] = None
    # Password for brokers that use it
    password: Optional[str] = None


class BrokerSessionOut(BaseModel):
    id: str
    broker: str
    client_id: Optional[str]
    is_active: bool
    expires_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class BrokerCredentialsOut(BaseModel):
    """Full saved credential details for a broker session."""
    broker: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # Credential fields (sensitive — only returned to the owning user)
    api_key: Optional[str]
    api_secret: Optional[str]
    client_id: Optional[str]
    access_token: Optional[str]
    refresh_token: Optional[str]
    request_token: Optional[str]
    totp_secret: Optional[str]
    password: Optional[str]
    expires_at: Optional[str]

    model_config = {"from_attributes": True}


class BrokerLoginUrlResponse(BaseModel):
    broker: str
    login_url: str
    instructions: str


