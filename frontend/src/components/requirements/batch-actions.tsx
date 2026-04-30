"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import { Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { batchConfirm, batchReject } from "@/lib/api/feedback";

interface BatchActionsProps {
  selectedIds: string[];
  onComplete: () => void;
}

export function BatchActions({ selectedIds, onComplete }: BatchActionsProps) {
  const t = useTranslations("requirements");
  const tc = useTranslations("common");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);

  const handleBatchConfirm = async () => {
    setLoading(true);
    try {
      const result = await batchConfirm(selectedIds);
      if (result.failed > 0) {
        toast.warning(
          t("batchConfirmSuccess", { succeeded: result.succeeded, total: result.total }),
        );
      } else {
        toast.success(
          t("batchConfirmSuccess", { succeeded: result.succeeded, total: result.total }),
        );
      }
      setConfirmOpen(false);
      onComplete();
    } catch (err) {
      console.error("[batch-actions] Batch confirm failed:", err);
      toast.error(tc("error"));
    } finally {
      setLoading(false);
    }
  };

  const handleBatchReject = async () => {
    if (!reason.trim()) return;
    setLoading(true);
    try {
      const result = await batchReject(selectedIds, reason.trim());
      if (result.failed > 0) {
        toast.warning(
          t("batchRejectSuccess", { succeeded: result.succeeded, total: result.total }),
        );
      } else {
        toast.success(
          t("batchRejectSuccess", { succeeded: result.succeeded, total: result.total }),
        );
      }
      setReason("");
      setRejectOpen(false);
      onComplete();
    } catch (err) {
      console.error("[batch-actions] Batch reject failed:", err);
      toast.error(tc("error"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="flex items-center gap-3 rounded-lg border bg-muted/50 px-4 py-2">
        <span className="text-sm font-medium">
          {t("selectedCount", { count: selectedIds.length })}
        </span>
        <Button
          size="sm"
          variant="outline"
          className="text-green-600 border-green-200 hover:bg-green-50"
          onClick={() => setConfirmOpen(true)}
        >
          <Check className="mr-1 h-4 w-4" />
          {t("batchConfirm")}
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="text-red-600 border-red-200 hover:bg-red-50"
          onClick={() => setRejectOpen(true)}
        >
          <X className="mr-1 h-4 w-4" />
          {t("batchReject")}
        </Button>
      </div>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("batchConfirm")}</DialogTitle>
            <DialogDescription>
              {t("batchConfirmMessage", { count: selectedIds.length })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmOpen(false)}
              disabled={loading}
            >
              {tc("cancel")}
            </Button>
            <Button onClick={handleBatchConfirm} disabled={loading}>
              {tc("confirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={rejectOpen}
        onOpenChange={(open) => {
          setRejectOpen(open);
          if (!open) setReason("");
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("batchReject")}</DialogTitle>
            <DialogDescription>
              {t("batchRejectMessage", { count: selectedIds.length })}
            </DialogDescription>
          </DialogHeader>
          <div className="py-2">
            <Textarea
              placeholder={t("rejectReasonPlaceholder")}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setRejectOpen(false);
                setReason("");
              }}
              disabled={loading}
            >
              {tc("cancel")}
            </Button>
            <Button
              variant="destructive"
              onClick={handleBatchReject}
              disabled={loading || !reason.trim()}
            >
              {tc("reject")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
