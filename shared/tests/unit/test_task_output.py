"""Tests for DiskTaskOutput — disk-backed streaming task output with delta reads."""

import asyncio

import pytest


@pytest.fixture()
def tmp_output_dir(tmp_path):
    return str(tmp_path / "task_output")


@pytest.fixture()
async def output(tmp_output_dir):
    from shared.infra.task_output import DiskTaskOutput
    out = DiskTaskOutput(task_id="test-task-001", base_dir=tmp_output_dir)
    yield out
    await out.close()


class TestAppendAndReadDelta:
    @pytest.mark.asyncio
    async def test_append_then_read_all(self, output):
        await output.append("hello world")
        content, offset = await output.read_delta(0)
        assert content == "hello world"
        assert offset == len("hello world")

    @pytest.mark.asyncio
    async def test_multiple_appends_delta_read(self, output):
        await output.append("first ")
        _, offset1 = await output.read_delta(0)
        await output.append("second")
        content, offset2 = await output.read_delta(offset1)
        assert content == "second"
        assert offset2 == offset1 + len("second")

    @pytest.mark.asyncio
    async def test_read_delta_at_end_returns_empty(self, output):
        await output.append("data")
        _, offset = await output.read_delta(0)
        content, new_offset = await output.read_delta(offset)
        assert content == ""
        assert new_offset == offset

    @pytest.mark.asyncio
    async def test_read_delta_nonexistent_file(self, output):
        content, offset = await output.read_delta(0)
        assert content == ""
        assert offset == 0


class TestReadAll:
    @pytest.mark.asyncio
    async def test_read_all(self, output):
        await output.append("part1")
        await output.append("part2")
        content = await output.read_all()
        assert content == "part1part2"


class TestSize:
    @pytest.mark.asyncio
    async def test_size_after_appends(self, output):
        await output.append("abc")
        assert await output.size() == 3
        await output.append("defgh")
        assert await output.size() == 8


class TestClose:
    @pytest.mark.asyncio
    async def test_close_empty_deletes_file(self, tmp_output_dir):
        from pathlib import Path

        from shared.infra.task_output import DiskTaskOutput

        out = DiskTaskOutput(task_id="empty-task", base_dir=tmp_output_dir)
        # Never appended — file doesn't exist
        await out.close()
        assert not Path(tmp_output_dir, "empty-task.output").exists()

    @pytest.mark.asyncio
    async def test_close_nonempty_preserves_file(self, tmp_output_dir):
        from pathlib import Path

        from shared.infra.task_output import DiskTaskOutput

        out = DiskTaskOutput(task_id="full-task", base_dir=tmp_output_dir)
        await out.append("data")
        await out.close()
        assert Path(tmp_output_dir, "full-task.output").exists()


class TestTaskIdValidation:
    def test_invalid_chars_raises(self, tmp_output_dir):
        from shared.infra.task_output import DiskTaskOutput
        with pytest.raises(ValueError):
            DiskTaskOutput(task_id="../../etc/passwd", base_dir=tmp_output_dir)

    def test_valid_id_accepted(self, tmp_output_dir):
        from shared.infra.task_output import DiskTaskOutput
        out = DiskTaskOutput(task_id="valid-task-123", base_dir=tmp_output_dir)
        assert out._task_id == "valid-task-123"


class TestCapEnforcement:
    @pytest.mark.asyncio
    async def test_cap_exceeded_raises(self, tmp_output_dir):
        from shared.infra.task_output import DiskTaskOutput, TaskOutputCapError

        # Use a tiny cap for testing
        out = DiskTaskOutput(
            task_id="big-task", base_dir=tmp_output_dir, max_bytes=100,
        )
        await out.append("x" * 50)
        with pytest.raises(TaskOutputCapError):
            await out.append("y" * 60)  # 50 + 60 = 110 > 100
        # Original data preserved
        content = await out.read_all()
        assert content == "x" * 50
        await out.close()


class TestAsyncIO:
    @pytest.mark.asyncio
    async def test_append_does_not_block_event_loop(self, output):
        """append() should use asyncio.to_thread, not block the event loop."""
        import unittest.mock
        with unittest.mock.patch("shared.infra.task_output.asyncio.to_thread", wraps=asyncio.to_thread) as mock_thread:
            await output.append("test data")
            assert mock_thread.call_count >= 1, "append should delegate file I/O to asyncio.to_thread"

    @pytest.mark.asyncio
    async def test_read_delta_does_not_block_event_loop(self, output):
        """read_delta() should use asyncio.to_thread."""
        await output.append("test data")
        import unittest.mock
        with unittest.mock.patch("shared.infra.task_output.asyncio.to_thread", wraps=asyncio.to_thread) as mock_thread:
            content, _ = await output.read_delta(0)
            assert content == "test data"
            assert mock_thread.call_count >= 1, "read_delta should delegate file I/O to asyncio.to_thread"


class TestConcurrentAppends:
    @pytest.mark.asyncio
    async def test_concurrent_appends_no_corruption(self, output):
        async def append_chunk(chunk: str):
            await output.append(chunk)

        chunks = [f"chunk{i}" for i in range(10)]
        await asyncio.gather(*[append_chunk(c) for c in chunks])

        content = await output.read_all()
        # All chunks present (order may vary with concurrent writes)
        for c in chunks:
            assert c in content
        assert await output.size() == sum(len(c) for c in chunks)
