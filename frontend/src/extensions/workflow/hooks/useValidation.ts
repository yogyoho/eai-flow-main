"use client";

import { useState } from "react";

import { workflowApi } from "../api";
import type { DAGValidationResult, WorkflowGraph } from "../types";

export function useValidation() {
  const [result, setResult] = useState<DAGValidationResult | null>(null);
  const [isValidating, setIsValidating] = useState(false);

  const validate = async (graph: WorkflowGraph) => {
    setIsValidating(true);
    try {
      const r = await workflowApi.validate(graph);
      setResult(r);
      return r;
    } finally {
      setIsValidating(false);
    }
  };

  return { result, isValidating, validate };
}
