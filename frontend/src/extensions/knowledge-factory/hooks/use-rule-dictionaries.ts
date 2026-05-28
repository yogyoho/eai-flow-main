"use client";

import { useEffect, useState } from "react";

import {
  DEFAULT_RULE_DICTIONARIES,
  type RuleDictionaries,
} from "@/extensions/knowledge-factory/types";

import { fetchRuleDictionaries } from "../complianceRulesApi";
import { mergeRuleDictionaries } from "../rule-dictionary-utils";

export function useRuleDictionaries() {
  const [dictionaries, setDictionaries] = useState<RuleDictionaries>(DEFAULT_RULE_DICTIONARIES);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const remote = await fetchRuleDictionaries();
        if (!cancelled) {
          setDictionaries(mergeRuleDictionaries(remote));
        }
      } catch {
        if (!cancelled) {
          setDictionaries(DEFAULT_RULE_DICTIONARIES);
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, []);

  return dictionaries;
}
