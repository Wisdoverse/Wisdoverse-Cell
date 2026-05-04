"use client";

import { AppErrorWidget } from "@/widgets/app-shell";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <AppErrorWidget error={error} reset={reset} />;
}
