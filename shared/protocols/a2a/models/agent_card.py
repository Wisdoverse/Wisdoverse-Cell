"""
A2A Agent Card Models

Defines the Agent Card and related models for agent discovery.
Based on Google's A2A Protocol Specification v0.3.0
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentProvider(BaseModel):
    """Information about the agent's provider organization."""

    model_config = ConfigDict(extra="forbid")

    organization: str = Field(..., description="Name of the organization providing the agent")
    url: str | None = Field(default=None, description="URL of the organization's website")


class AgentCapabilities(BaseModel):
    """Describes what features the agent supports."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    streaming: bool = Field(default=False, description="Whether the agent supports streaming responses")
    push_notifications: bool = Field(
        default=False, alias="pushNotifications", description="Whether the agent supports push notifications"
    )
    state_transition_history: bool = Field(
        default=False,
        alias="stateTransitionHistory",
        description="Whether the agent maintains state transition history",
    )


class SecurityScheme(BaseModel):
    """Security scheme definition following OpenAPI 3.0 style."""

    model_config = ConfigDict(extra="allow")

    type: Literal["apiKey", "http", "oauth2", "openIdConnect"] = Field(
        ..., description="Type of security scheme"
    )
    # For apiKey
    name: str | None = Field(default=None, description="Name of the API key header/query parameter")
    in_location: Literal["header", "query", "cookie"] | None = Field(
        default=None, alias="in", description="Location of the API key"
    )
    # For http
    scheme: str | None = Field(default=None, description="HTTP auth scheme (e.g., 'bearer')")
    bearer_format: str | None = Field(default=None, alias="bearerFormat", description="Bearer token format")
    # For openIdConnect
    open_id_connect_url: str | None = Field(
        default=None, alias="openIdConnectUrl", description="OpenID Connect discovery URL"
    )


class AgentInterface(BaseModel):
    """Additional interface endpoint for the agent."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(..., description="URL of the interface endpoint")
    transport: Literal["JSONRPC", "GRPC", "HTTP+JSON"] = Field(
        ..., description="Transport protocol for this interface"
    )


class AgentSkill(BaseModel):
    """Describes a specific capability/skill of the agent."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique identifier for the skill")
    name: str = Field(..., description="Human-readable name of the skill")
    description: str = Field(..., description="Detailed description of what the skill does")
    tags: list[str] = Field(default_factory=list, description="Tags for categorizing the skill")
    examples: list[str] = Field(
        default_factory=list, description="Example prompts or use cases for this skill"
    )
    input_modes: list[str] = Field(
        default_factory=lambda: ["text/plain"],
        alias="inputModes",
        description="Supported input MIME types",
    )
    output_modes: list[str] = Field(
        default_factory=lambda: ["text/plain"],
        alias="outputModes",
        description="Supported output MIME types",
    )


class AgentCard(BaseModel):
    """
    Agent Card - A JSON manifest describing an agent's identity and capabilities.

    This is the primary discovery mechanism for A2A protocol.
    Served at /.well-known/agent.json
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # Identity
    name: str = Field(..., description="Human-readable name of the agent")
    description: str = Field(..., description="Description of what the agent does")
    protocol_version: str = Field(
        default="0.3.0", alias="protocolVersion", description="A2A protocol version"
    )

    # Endpoint
    url: str = Field(..., description="Primary endpoint URL for the agent")
    preferred_transport: Literal["JSONRPC", "GRPC", "HTTP+JSON"] = Field(
        default="JSONRPC", alias="preferredTransport", description="Preferred transport protocol"
    )
    additional_interfaces: list[AgentInterface] = Field(
        default_factory=list,
        alias="additionalInterfaces",
        description="Additional transport interfaces",
    )

    # Provider information
    provider: AgentProvider | None = Field(default=None, description="Information about the agent provider")

    # Capabilities
    capabilities: AgentCapabilities = Field(
        default_factory=lambda: AgentCapabilities(), description="Agent capabilities"
    )

    # Security
    security_schemes: dict[str, SecurityScheme] = Field(
        default_factory=dict, alias="securitySchemes", description="Available security schemes"
    )
    security: list[dict[str, list[str]]] = Field(
        default_factory=list, description="Required security (scheme name -> scopes)"
    )

    # Input/Output
    default_input_modes: list[str] = Field(
        default_factory=lambda: ["text/plain", "application/json"],
        alias="defaultInputModes",
        description="Default supported input MIME types",
    )
    default_output_modes: list[str] = Field(
        default_factory=lambda: ["text/plain", "application/json"],
        alias="defaultOutputModes",
        description="Default supported output MIME types",
    )

    # Skills
    skills: list[AgentSkill] = Field(
        default_factory=list, description="List of skills/capabilities the agent offers"
    )

    # Extended card support
    supports_authenticated_extended_card: bool = Field(
        default=False,
        alias="supportsAuthenticatedExtendedCard",
        description="Whether agent provides extended card after auth",
    )

    # Optional metadata
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata about the agent"
    )

    def to_well_known_json(self) -> dict:
        """Export as JSON suitable for /.well-known/agent.json endpoint."""
        return self.model_dump(by_alias=True, exclude_none=True)
