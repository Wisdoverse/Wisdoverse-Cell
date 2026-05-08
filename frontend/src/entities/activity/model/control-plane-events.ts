import type { ActivityEvent, ControlPlaneAgentRun } from "@/lib/api/types";

function eventTimestamp(run: ControlPlaneAgentRun): string {
  return run.completed_at ?? run.started_at;
}

export function controlPlaneRunsToActivityEvents(
  runs: ControlPlaneAgentRun[],
  describeRun: (run: ControlPlaneAgentRun) => string,
): ActivityEvent[] {
  return runs.map((run) => ({
    id: run.run_id,
    agent_id: run.agent_id,
    event_type: `agent_run.${run.status}`,
    description: describeRun(run),
    payload: {
      run_id: run.run_id,
      trace_id: run.trace_id,
      goal_id: run.goal_id,
      work_item_id: run.work_item_id,
      status: run.status,
      error_category: run.error_category,
      error_message: run.error_message,
      cost_usd: run.cost_usd,
      input_tokens: run.input_tokens,
      output_tokens: run.output_tokens,
    },
    timestamp: eventTimestamp(run),
  }));
}
