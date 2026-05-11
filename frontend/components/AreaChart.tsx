"use client";

import { useEffect, useRef } from "react";
import { createChart, ColorType, type UTCTimestamp } from "lightweight-charts";
import type { ChartPoint } from "@/types";

interface AreaChartProps {
  data: ChartPoint[];
  height?: number;
  lineColor?: string;
  topColor?: string;
  bottomColor?: string;
  title?: string;
  formatValue?: (v: number) => string;
}

export default function AreaChart({
  data,
  height = 200,
  lineColor = "#3b82f6",
  topColor = "#3b82f630",
  bottomColor = "rgba(0,0,0,0)",
  title,
  formatValue,
}: AreaChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

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
      timeScale: { borderColor: "#2d3144", timeVisible: true },
      rightPriceScale: { borderColor: "#2d3144" },
      crosshair: { mode: 1 },
    });

    const series = chart.addAreaSeries({
      lineColor,
      topColor,
      bottomColor,
      lineWidth: 2,
    });

    series.setData(
      data.map((d) => ({ time: d.time as UTCTimestamp, value: d.value }))
    );

    if (formatValue) {
      series.applyOptions({
        priceFormat: { type: "custom", formatter: formatValue, minMove: 0.01 },
      });
    }

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
    };
  }, [data, height, lineColor, topColor, bottomColor, formatValue]);

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg text-sm"
        style={{
          height,
          background: "var(--surface-2)",
          color: "var(--text-secondary)",
          border: "1px solid var(--border)",
        }}
      >
        {title ? `${title} — ` : ""}No data yet. Run a scheduler cycle to generate snapshots.
      </div>
    );
  }

  return <div ref={containerRef} className="rounded-lg overflow-hidden w-full" style={{ height }} />;
}
