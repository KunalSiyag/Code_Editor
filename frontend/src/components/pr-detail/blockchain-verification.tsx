"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Link2,
  ExternalLink,
  CheckCircle2,
  Clock,
  Copy,
  Check,
  Shield,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { BlockchainVerification } from "@/lib/types";

interface BlockchainVerificationPanelProps {
  verification?: BlockchainVerification;
}

export function BlockchainVerificationPanel({
  verification,
}: BlockchainVerificationPanelProps) {
  const [copied, setCopied] = useState(false);
  const [verified, setVerified] = useState(false);

  useEffect(() => {
    if (verification?.verified) {
      const timer = setTimeout(() => setVerified(true), 1000);
      return () => clearTimeout(timer);
    }
    setVerified(false);
  }, [verification?.verified]);

  const copyHash = async () => {
    if (verification?.transactionHash) {
      await navigator.clipboard.writeText(verification.transactionHash);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (!verification) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="rounded-xl border border-border bg-card p-6"
      >
        <div className="flex items-center justify-center gap-3 text-muted-foreground">
          <Clock className="h-5 w-5" />
          <span>No blockchain record is available for this scan yet.</span>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-border bg-card overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-border px-4 py-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
          <Link2 className="h-4 w-4 text-primary" />
        </div>
        <div className="flex-1">
          <h3 className="font-semibold text-foreground">
            Blockchain Verification
          </h3>
          <p className="text-xs text-muted-foreground">
            Immutable audit record on {verification.network}
          </p>
        </div>
        <Badge
          className={cn(
            verified
              ? "bg-success/10 text-success border-success/30"
              : "bg-warning/10 text-warning border-warning/30"
          )}
        >
          {verified ? (
            <span className="flex items-center gap-1">
              <CheckCircle2 className="h-3 w-3" />
              Verified
            </span>
          ) : (
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              Pending
            </span>
          )}
        </Badge>
      </div>

      <div className="p-4">
        {/* Verification Animation */}
        {verified && (
          <motion.div
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            className="mb-4 flex items-center justify-center"
          >
            <div className="relative">
              <motion.div
                className="absolute inset-0 rounded-full bg-success/20"
                animate={{
                  scale: [1, 1.5, 1],
                  opacity: [0.5, 0, 0.5],
                }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                  ease: "easeInOut",
                }}
              />
              <div className="relative flex h-16 w-16 items-center justify-center rounded-full bg-success/10">
                <Shield className="h-8 w-8 text-success" />
              </div>
            </div>
          </motion.div>
        )}

        {/* Transaction Details */}
        <div className="space-y-4">
          {/* Transaction Hash */}
          <div>
            <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Transaction Hash
            </label>
            <div className="mt-1 flex items-center gap-2">
              <code className="flex-1 overflow-hidden rounded-lg bg-muted/30 px-3 py-2 font-mono text-xs text-foreground">
                <span className="block truncate">
                  {verification.transactionHash}
                </span>
              </code>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-9 w-9 shrink-0 bg-transparent"
                      onClick={copyHash}
                    >
                      {copied ? (
                        <Check className="h-4 w-4 text-success" />
                      ) : (
                        <Copy className="h-4 w-4" />
                      )}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    {copied ? "Copied!" : "Copy hash"}
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
          </div>

          {verification.auditHash &&
          verification.auditHash !== verification.transactionHash ? (
            <div>
              <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Audit Hash
              </label>
              <code className="mt-1 block overflow-hidden rounded-lg bg-muted/30 px-3 py-2 font-mono text-xs text-foreground">
                <span className="block truncate">{verification.auditHash}</span>
              </code>
            </div>
          ) : null}

          {/* Block & Timestamp */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Block Number
              </label>
              <p className="mt-1 font-mono text-sm text-foreground">
                {verification.blockNumber > 0
                  ? verification.blockNumber.toLocaleString()
                  : "Pending"}
              </p>
            </div>
            <div>
              <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Timestamp
              </label>
              <p className="mt-1 text-sm text-foreground">
                {verification.timestamp
                  ? new Date(verification.timestamp).toLocaleString()
                  : "Pending"}
              </p>
            </div>
          </div>

          {/* Network */}
          <div>
            <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Network
            </label>
            <p className="mt-1 text-sm text-foreground">
              {verification.network}
            </p>
          </div>

          {/* Explorer Link */}
          {verification.explorerUrl ? (
            <Button asChild className="w-full bg-transparent" variant="outline">
              <a
                href={verification.explorerUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center gap-2"
              >
                <ExternalLink className="h-4 w-4" />
                View on Block Explorer
              </a>
            </Button>
          ) : (
            <Button className="w-full bg-transparent" variant="outline" disabled>
              Explorer link unavailable
            </Button>
          )}
        </div>

        {/* Immutability Notice */}
        <div className="mt-4 rounded-lg bg-muted/30 p-3">
          <p className="text-xs text-muted-foreground">
            <strong className="text-foreground">Immutable Record:</strong> This
            {verified
              ? " audit result has been permanently recorded on the blockchain."
              : " audit hash has been generated and is ready for blockchain anchoring."}{" "}
            {verified
              ? "The record cannot be modified or deleted, ensuring tamper-proof verification of the security analysis."
              : "Configure the blockchain environment variables in the backend to enable live on-chain confirmation."}
          </p>
        </div>
      </div>
    </motion.div>
  );
}
