"use client";

import { Fragment, useState } from "react";
import { useTranslations } from "next-intl";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/empty-state";
import { getSession } from "@/lib/api/messages";
import type { MessageSearchResult, MessageSession } from "@/lib/api/types";

interface MessageTableProps {
  data: MessageSearchResult[];
  isLoading: boolean;
}

function formatTime(iso: string): string {
  const date = new Date(iso);
  if (isNaN(date.getTime())) {
    console.warn("[message-table] Invalid timestamp received:", iso);
    return iso;
  }
  return date.toLocaleString();
}

function truncate(text: string, max: number): string {
  return text.length > max ? text.slice(0, max) + "..." : text;
}

export function MessageTable({ data, isLoading }: MessageTableProps) {
  const t = useTranslations("messages");
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [session, setSession] = useState<MessageSession | null>(null);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [sessionError, setSessionError] = useState(false);

  async function handleRowClick(row: MessageSearchResult) {
    if (!row.session_id) return;

    if (expandedRow === row.id) {
      setExpandedRow(null);
      setSession(null);
      setSessionError(false);
      return;
    }

    setExpandedRow(row.id);
    setSessionError(false);
    setSessionLoading(true);
    try {
      const data = await getSession(row.session_id);
      setSession(data);
    } catch (err) {
      console.error("[message-table] Failed to load session:", row.session_id, err);
      setSession(null);
      setSessionError(true);
    } finally {
      setSessionLoading(false);
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (data.length === 0) {
    return <EmptyState />;
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("sender")}</TableHead>
            <TableHead>{t("content")}</TableHead>
            <TableHead>{t("source")}</TableHead>
            <TableHead>{t("time")}</TableHead>
            <TableHead>{t("extracted")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((row) => (
            <Fragment key={row.id}>
              <TableRow
                className={row.session_id ? "cursor-pointer" : ""}
                onClick={() => handleRowClick(row)}
              >
                <TableCell className="font-medium">
                  {row.sender_name}
                </TableCell>
                <TableCell className="max-w-xs">
                  {truncate(row.content, 80)}
                </TableCell>
                <TableCell>{row.message_type}</TableCell>
                <TableCell className="whitespace-nowrap">
                  {formatTime(row.sent_at)}
                </TableCell>
                <TableCell>
                  {row.extracted && (
                    <Badge variant="secondary">{t("extracted")}</Badge>
                  )}
                </TableCell>
              </TableRow>
              {expandedRow === row.id && (
                <TableRow key={`${row.id}-session`}>
                  <TableCell colSpan={5} className="bg-muted/50 p-4">
                    {sessionLoading ? (
                      <div className="space-y-2">
                        {[1, 2, 3].map((i) => (
                          <Skeleton key={i} className="h-8 w-full" />
                        ))}
                      </div>
                    ) : sessionError ? (
                      <p className="text-sm text-destructive py-2">
                        {t("sessionLoadError")}
                      </p>
                    ) : session ? (
                      <div className="space-y-2">
                        {session.messages.map((msg) => (
                          <div
                            key={msg.id}
                            className="flex gap-3 text-sm rounded-lg border bg-background p-3"
                          >
                            <span className="font-medium shrink-0">
                              {msg.sender_name}
                            </span>
                            <span className="text-muted-foreground flex-1">
                              {msg.content}
                            </span>
                            <span className="text-xs text-muted-foreground shrink-0">
                              {formatTime(msg.sent_at)}
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </TableCell>
                </TableRow>
              )}
            </Fragment>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
