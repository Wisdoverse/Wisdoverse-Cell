"""Tests for A2A protocol models."""


from shared.protocols.a2a.models import (
    AgentCapabilities,
    AgentCard,
    AgentProvider,
    AgentSkill,
    Artifact,
    DataPart,
    FileContent,
    FilePart,
    Message,
    MessageSendParams,
    SecurityScheme,
    Task,
    TaskCancelParams,
    TaskGetParams,
    TaskState,
    TaskStatus,
    TextPart,
)


class TestAgentCard:
    """Tests for AgentCard model."""

    def test_minimal_agent_card(self):
        """Test creating a minimal agent card."""
        card = AgentCard(
            name="Test Agent",
            description="A test agent",
            url="http://localhost:8000/a2a",
        )

        assert card.name == "Test Agent"
        assert card.description == "A test agent"
        assert card.url == "http://localhost:8000/a2a"
        assert card.protocol_version == "0.3.0"
        assert card.preferred_transport == "JSONRPC"

    def test_full_agent_card(self):
        """Test creating a full agent card with all fields."""
        card = AgentCard(
            name="Full Agent",
            description="A fully configured agent",
            url="http://localhost:8000/a2a",
            provider=AgentProvider(
                organization="Test Org",
                url="https://test.org",
            ),
            capabilities=AgentCapabilities(
                streaming=True,
                pushNotifications=True,  # Use alias
            ),
            skills=[
                AgentSkill(
                    id="test-skill",
                    name="Test Skill",
                    description="A test skill",
                    tags=["test", "demo"],
                    examples=["Do something"],
                )
            ],
            security_schemes={
                "bearer": SecurityScheme(type="http", scheme="bearer")
            },
        )

        assert card.provider.organization == "Test Org"
        assert card.capabilities.streaming is True
        assert len(card.skills) == 1
        assert card.skills[0].id == "test-skill"

    def test_agent_card_serialization(self):
        """Test AgentCard JSON serialization with aliases."""
        card = AgentCard(
            name="Serialization Test",
            description="Test serialization",
            url="http://localhost:8000/a2a",
            capabilities=AgentCapabilities(
                streaming=True,
                pushNotifications=True,  # Use alias
            ),
        )

        json_data = card.to_well_known_json()

        assert "protocolVersion" in json_data
        assert "pushNotifications" in json_data["capabilities"]
        assert json_data["capabilities"]["pushNotifications"] is True


class TestMessage:
    """Tests for Message model."""

    def test_text_message(self):
        """Test creating a text message."""
        msg = Message.text("Hello, world!")

        assert msg.role == "user"
        assert len(msg.parts) == 1
        assert isinstance(msg.parts[0], TextPart)
        assert msg.parts[0].text == "Hello, world!"

    def test_data_message(self):
        """Test creating a data message."""
        data = {"key": "value", "count": 42}
        msg = Message.data(data)

        assert msg.role == "agent"
        assert len(msg.parts) == 1
        assert isinstance(msg.parts[0], DataPart)
        assert msg.parts[0].data == data

    def test_message_with_file(self):
        """Test creating a message with file."""
        file_part = FilePart(
            file=FileContent(
                name="test.txt",
                mimeType="text/plain",  # Use alias
                bytes="SGVsbG8gV29ybGQ=",  # Base64 "Hello World"
            )
        )
        msg = Message(role="user", parts=[file_part])

        assert msg.parts[0].file.name == "test.txt"

    def test_get_text_content(self):
        """Test extracting text content from message."""
        msg = Message(
            role="user",
            parts=[
                TextPart(text="First line"),
                TextPart(text="Second line"),
            ],
        )

        assert msg.get_text_content() == "First line\nSecond line"

    def test_get_data_content(self):
        """Test extracting data content from message."""
        data = {"result": "success"}
        msg = Message.data(data)

        assert msg.get_data_content() == data


class TestTask:
    """Tests for Task model."""

    def test_task_creation(self):
        """Test creating a new task."""
        task = Task()

        assert task.id.startswith("task_")
        assert task.context_id.startswith("ctx_")
        assert task.status.state == TaskStatus.SUBMITTED

    def test_task_state_transitions(self):
        """Test task state transitions."""
        task = Task()

        # Submitted -> Working
        task.update_status(TaskState.working("Processing..."))
        assert task.status.state == TaskStatus.WORKING
        assert task.status.message is not None

        # Working -> Completed
        task.update_status(TaskState.completed("Done!"))
        assert task.status.state == TaskStatus.COMPLETED
        assert task.is_terminal() is True

    def test_task_add_message(self):
        """Test adding messages to task."""
        task = Task()
        msg = Message.text("Hello")

        task.add_message(msg)

        assert len(task.history) == 1
        assert task.history[0].task_id == task.id
        assert task.history[0].context_id == task.context_id

    def test_task_add_artifact(self):
        """Test adding artifacts to task."""
        task = Task()
        artifact = Artifact(
            name="result.json",
            parts=[DataPart(data={"result": "success"})],
        )

        task.add_artifact(artifact)

        assert len(task.artifacts) == 1
        assert task.artifacts[0].name == "result.json"

    def test_task_terminal_states(self):
        """Test terminal state detection."""
        task = Task()

        task.update_status(TaskState.submitted())
        assert task.is_terminal() is False

        task.update_status(TaskState.working())
        assert task.is_terminal() is False

        task.update_status(TaskState.input_required("Need more info"))
        assert task.is_terminal() is False

        task.update_status(TaskState.completed())
        assert task.is_terminal() is True

        task2 = Task()
        task2.update_status(TaskState.failed("Error"))
        assert task2.is_terminal() is True

        task3 = Task()
        task3.update_status(TaskState.canceled("User canceled"))
        assert task3.is_terminal() is True


class TestTaskState:
    """Tests for TaskState factory methods."""

    def test_submitted_state(self):
        """Test creating submitted state."""
        state = TaskState.submitted()
        assert state.state == TaskStatus.SUBMITTED

    def test_working_state(self):
        """Test creating working state."""
        state = TaskState.working("Analyzing...")
        assert state.state == TaskStatus.WORKING
        assert state.message is not None
        assert state.message.get_text_content() == "Analyzing..."

    def test_input_required_state(self):
        """Test creating input-required state."""
        state = TaskState.input_required("Please provide more details")
        assert state.state == TaskStatus.INPUT_REQUIRED
        assert "more details" in state.message.get_text_content()

    def test_completed_state(self):
        """Test creating completed state."""
        state = TaskState.completed("Task finished successfully")
        assert state.state == TaskStatus.COMPLETED

    def test_failed_state(self):
        """Test creating failed state."""
        state = TaskState.failed("Something went wrong")
        assert state.state == TaskStatus.FAILED
        assert "wrong" in state.message.get_text_content()

    def test_canceled_state(self):
        """Test creating canceled state."""
        state = TaskState.canceled("User requested cancellation")
        assert state.state == TaskStatus.CANCELED


class TestMessageSendParams:
    """Tests for MessageSendParams model."""

    def test_params_creation(self):
        """Test creating message send params."""
        msg = Message.text("Hello")
        params = MessageSendParams(
            message=msg,
            context_id="ctx_123",
            configuration={"max_tokens": 1000},
        )

        assert params.message == msg
        assert params.context_id == "ctx_123"
        assert params.configuration["max_tokens"] == 1000


class TestTaskGetParams:
    """Tests for TaskGetParams model."""

    def test_params_serialization(self):
        """Test params serialization with aliases."""
        params = TaskGetParams(task_id="task_123", history_length=10)

        data = params.model_dump(by_alias=True)
        assert data["taskId"] == "task_123"
        assert data["historyLength"] == 10


class TestTaskCancelParams:
    """Tests for TaskCancelParams model."""

    def test_params_creation(self):
        """Test creating cancel params."""
        params = TaskCancelParams(
            task_id="task_123",
            reason="User requested cancellation",
        )

        assert params.task_id == "task_123"
        assert params.reason == "User requested cancellation"
