import { useEffect, useRef } from "react";
import { createChart, type IChartApi, type ISeriesApi, type Time, type UTCTimestamp } from "lightweight-charts";
import type { Bar } from "../types";

function toChartTime(time: string): Time {
  if (/^\d{4}-\d{2}-\d{2}$/.test(time)) {
    return time;
  }
  const ms = Date.parse(time);
  if (Number.isNaN(ms)) {
    return time;
  }
  return Math.floor(ms / 1000) as UTCTimestamp;
}

export function KLineChart({ bars }: { bars: Bar[] }) {
  const host = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    if (!host.current) {
      return;
    }
    const chart = createChart(host.current, {
      layout: {
        background: { color: "#faf6ec" },
        textColor: "#687062",
      },
      grid: {
        vertLines: { color: "#c5c8b4" },
        horzLines: { color: "#c5c8b4" },
      },
      width: host.current.clientWidth,
      height: host.current.clientHeight,
      timeScale: { timeVisible: true, secondsVisible: false },
    });
    const series = chart.addCandlestickSeries({
      upColor: "#687748",
      downColor: "#b96458",
      borderVisible: false,
      wickUpColor: "#687748",
      wickDownColor: "#b96458",
    });
    chartRef.current = chart;
    seriesRef.current = series;
    const onResize = () => {
      if (!host.current) {
        return;
      }
      chart.applyOptions({ width: host.current.clientWidth, height: host.current.clientHeight });
    };
    const observer = new ResizeObserver(onResize);
    observer.observe(host.current);
    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current) {
      return;
    }
    seriesRef.current.setData(
      bars.map((bar) => ({
        time: toChartTime(bar.time),
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      })),
    );
    chartRef.current?.timeScale().fitContent();
  }, [bars]);

  return <div className="chart-host" ref={host} />;
}
