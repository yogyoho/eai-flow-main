"use client";

import { useState } from "react";

import { workflowApi } from "../api";
import type { DAGValidationResult } from "../types";

export function useValidation() {
  const [result, setResult] = useState<DAGValidationResult | null>(null);
  const [isValidating, setIsValidating] = useState(false);

  const validate = async (graph: { nodes: unknown[]; edges: unknown[] }) => {
    setIsValidating(true);
    try {
      const r = await workflowApi.validate(graph as Parameters<typeof workflowApi.validate>[0]);
      setResult(r);
      return r;
    } finally {
      setIsValidating(false);
    }
  };

  return { result, isValidating, validate };
}
