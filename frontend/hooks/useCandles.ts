"use client";

import { useApi } from "./useApi";
import { candleService } from "@/services/api";
import type { Candle } from "@/types";

export function useCandles(symbol: string, timeframe: string, limit = 200) {
  return useApi<Candle[]>(
    () => candleService.getCandles(symbol, timeframe, limit),
    [symbol, timeframe, limit]
  );
}
