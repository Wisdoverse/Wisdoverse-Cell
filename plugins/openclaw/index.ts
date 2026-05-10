/**
 * Wisdoverse Cell Channel Plugin for OpenClaw
 *
 * Registers a "wisdoverse-cell" channel that bridges OpenClaw platforms
 * to Wisdoverse Cell's AI agent system via WebSocket JSON-RPC.
 */

import type { OpenClawPluginAPI, ChannelMessage, ChannelConfig } from "openclaw";

interface ProjectCellStatus {
  connected: boolean;
  device_id: string;
  uptime_seconds: number;
}

let startTime: number;

export default function register(api: OpenClawPluginAPI): void {
  startTime = Date.now();

  // Register the Wisdoverse Cell channel
  api.registerChannel({
    id: "wisdoverse-cell",
    name: "Wisdoverse Cell",
    description: "Route messages through Wisdoverse Cell AI agents",

    async onMessage(message: ChannelMessage): Promise<void> {
      // Forward inbound messages to Wisdoverse Cell adapter via gateway event
      await api.emitEvent("channel.message", {
        channel: "wisdoverse-cell",
        message_id: message.id,
        chat_id: message.chatId,
        chat_type: message.chatType ?? "private",
        sender: {
          id: message.senderId,
          name: message.senderName ?? "",
        },
        content: message.content,
        message_type: message.type ?? "text",
        timestamp: Math.floor(Date.now() / 1000),
        mentions: message.mentions ?? [],
        attachments: message.attachments ?? [],
      });
    },

    async onAction(callback: Record<string, unknown>): Promise<void> {
      await api.emitEvent("channel.action", {
        channel: "wisdoverse-cell",
        ...callback,
      });
    },
  });

  // Register Wisdoverse Cell agent tools
  api.registerTool({
    name: "wisdoverse-cell.query",
    description: "Send a query to Wisdoverse Cell AI agents and get a response",
    parameters: {
      query: { type: "string", description: "The query text", required: true },
      agent: { type: "string", description: "Target agent ID (optional)" },
      context: { type: "object", description: "Additional context" },
    },
    async execute(params: Record<string, unknown>): Promise<unknown> {
      return api.callRPC("wisdoverse-cell.query", params);
    },
  });

  // Register status RPC method
  api.registerRPC("wisdoverse-cell.status", async (): Promise<ProjectCellStatus> => {
    const config: ChannelConfig = api.getConfig();
    return {
      connected: api.isChannelConnected("wisdoverse-cell"),
      device_id: (config.PROJECTCELL_DEVICE_ID as string) ?? "wisdoverse-cell",
      uptime_seconds: Math.floor((Date.now() - startTime) / 1000),
    };
  });

  api.log("info", "Wisdoverse Cell plugin registered");
}
