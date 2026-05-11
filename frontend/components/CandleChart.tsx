"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  type IChartApi,
  type UTCTimestamp,
} from "lightweight-charts";
import type { Candle } from "@/types";

interface CandleChartProps {
  candles: Candle[];
  height?: number;
}

export default function CandleChart({ candles, height = 400 }: CandleChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#1a1d27" },
        textColor: "#8892a4",
      },
      grid: {
        vertLines: { color: "#2d3144" },
        horzLines: { color: "#2d3144" },
      },
      width: containerRef.current.clientWidth,
      height,
      timeScale: {
        borderColor: "#2d3144",
        timeVisible: true,
      },
      rightPriceScale: { borderColor: "#2d3144" },
    });

    chartRef.current = chart;

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    const volumeSeries = chart.addHistogramSeries({
      color: "#3b82f6",
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });

    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    const candleData = candles.map((c) => ({
      time: Math.floor(new Date(c.timestamp_utc).getTime() / 1000) as UTCTimestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    const volumeData = candles.map((c) => ({
      time: Math.floor(new Date(c.timestamp_utc).getTime() / 1000) as UTCTimestamp,
      value: c.volume,
      color: c.close >= c.open ? "#22c55e55" : "#ef444455",
    }));

    candleSeries.setData(candleData);
    volumeSeries.setData(volumeData);
    chart.timeScale().fitContent();

    const observer = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [candles, height]);

  if (candles.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg text-sm"
        style={{
          height,
          background: "var(--surface)",
          color: "var(--text-secondary)",
          border: "1px solid var(--border)",
        }}
      >
        No candle data. Click &quot;Load Data&quot; to fetch candles.
      </div>
    );
  }

  return <div ref={containerRef} className="rounded-lg overflow-hidden w-full" style={{ height }} />;
}
