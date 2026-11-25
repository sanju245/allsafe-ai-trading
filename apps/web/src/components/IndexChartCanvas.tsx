"use client";

import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries, ColorType, CrosshairMode, LineStyle, TickMarkType, createChart,
  type CandlestickData, type IChartApi, type IPriceLine, type ISeriesApi, type Time, type UTCTimestamp,
} from "lightweight-charts";
import { formatPrice, formatStamp, type Bar, type ChartMark, type SignalLevels } from "@/lib/indexChart";

const intraday = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const tradingDay = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", day: "numeric", month: "short" });
const asTime = (n: number) => n as UTCTimestamp;
const datum = (b: Bar): CandlestickData => ({ ...b, time: asTime(b.time) });
const sameBar = (a: Bar, b: Bar) => a.time === b.time && a.open === b.open && a.high === b.high && a.low === b.low && a.close === b.close;

type Props = {
  bars: Bar[]; marks: ChartMark[]; forming: Bar | null; realPrice?: number; priceLabel: string; loading: boolean;
  levels?: SignalLevels;
};

export default function IndexChartCanvas({ bars, marks, forming, realPrice, priceLabel, loading, levels }: Props) {
  const frame = useRef<HTMLDivElement>(null);
  const host = useRef<HTMLDivElement>(null);
  const overlay = useRef<HTMLDivElement>(null);
  const api = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const line = useRef<IPriceLine | null>(null);
  const drawn = useRef<{ bars: Bar[]; forming: Bar | null }>({ bars: [], forming: null });
  const reposition = useRef<() => void>(() => {});
  const [hovered, setHovered] = useState<Bar | null>(null);
  const [showSignals, setShowSignals] = useState(true);
  const [rangeSize, setRangeSize] = useState(0);
  const [full, setFull] = useState(false);
  const last = forming ?? bars.at(-1);
  const selected = hovered ?? last;

  useEffect(() => {
    if (!host.current || !overlay.current) return;
    const layer = overlay.current;
    const chart = createChart(host.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "#ffffff" }, textColor: "#4e5667", fontFamily: "Inter, Arial, sans-serif", fontSize: 12, attributionLogo: true },
      grid: { vertLines: { color: "#edf0f3" }, horzLines: { color: "#edf0f3" } },
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: "#788395", style: LineStyle.Dashed, labelBackgroundColor: "#293447" },
        horzLine: { color: "#788395", style: LineStyle.Dashed, labelBackgroundColor: "#293447" } },
      rightPriceScale: { borderColor: "#dbe0e6", scaleMargins: { top: 0.13, bottom: 0.14 }, minimumWidth: 75 },
      timeScale: { borderColor: "#dbe0e6", timeVisible: true, secondsVisible: false, rightOffset: 4, barSpacing: 12,
        minBarSpacing: 0.5, fixLeftEdge: true, lockVisibleTimeRangeOnResize: true, allowShiftVisibleRangeOnWhitespaceReplacement: true,
        tickMarkFormatter: (time: Time, kind: TickMarkType) =>
          (kind === TickMarkType.Time || kind === TickMarkType.TimeWithSeconds ? intraday : tradingDay).format(Number(time) * 1000) },
      localization: { locale: "en-IN", timeFormatter: (t: Time) => formatStamp(Number(t)) + " IST", priceFormatter: formatPrice },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
    });
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#299d76", downColor: "#ef5350", wickUpColor: "#299d76", wickDownColor: "#ef5350",
      borderVisible: false, priceLineVisible: false, lastValueVisible: false,
    });
    api.current = chart;
    series.current = candles;
    let raf = 0;
    const layout = () => {
      raf = 0;
      const { width, height } = chart.paneSize();
      layer.style.width = width + "px";
      layer.style.height = height + "px";
      for (const node of layer.children) {
        const badge = node as HTMLElement;
        const x = chart.timeScale().timeToCoordinate(asTime(Number(badge.dataset.time)));
        const wick = candles.priceToCoordinate(Number(badge.dataset.price));
        const y = wick === null ? null : wick + (badge.dataset.side === "BUY" ? 8 : -8);
        if (x === null || y === null || x < 0 || x > width || y < 0 || y > height) {
          badge.style.visibility = "hidden";
        } else {
          badge.style.left = x + "px";
          badge.style.top = y + "px";
          badge.style.visibility = "visible";
        }
      }
    };
    const schedule = () => { if (!raf) raf = requestAnimationFrame(layout); };
    reposition.current = schedule;
    const primitive = { updateAllViews: schedule };
    candles.attachPrimitive(primitive);
    chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (range) setRangeSize(Math.round(range.to - range.from));
      schedule();
    });
    chart.subscribeCrosshairMove((event) => {
      const item = event.seriesData.get(candles);
      setHovered(item && "open" in item ? { time: Number(item.time), open: item.open, high: item.high, low: item.low, close: item.close } : null);
    });
    const onFullscreen = () => setFull(document.fullscreenElement === frame.current);
    document.addEventListener("fullscreenchange", onFullscreen);
    return () => {
      document.removeEventListener("fullscreenchange", onFullscreen);
      candles.detachPrimitive(primitive);
      cancelAnimationFrame(raf);
      reposition.current = () => {};
      api.current = null;
      series.current = null;
      line.current = null;
      drawn.current = { bars: [], forming: null };
      chart.remove();
    };
  }, []);

  useEffect(() => {
    const chart = api.current, candleSeries = series.current;
    if (!chart || !candleSeries) return;
    const before = drawn.current;
    const samePrefix = before.bars.length <= bars.length && (before.bars === bars || before.bars.every((bar, i) => sameBar(bar, bars[i])));
    const scale = chart.timeScale();
    const historicalView = scale.scrollPosition() < -1 ? scale.getVisibleLogicalRange() : null;
    const append = bars.length > before.bars.length;
    const replaceTail = before.forming && (append || !forming || before.forming.time !== forming.time);
    if (!samePrefix || !before.bars.length) {
      candleSeries.setData(bars.map(datum));
    } else {
      if (replaceTail) candleSeries.pop(1);
      for (let i = before.bars.length; i < bars.length; i++) candleSeries.update(datum(bars[i]));
    }
    if (forming && (!before.forming || !sameBar(before.forming, forming) || !samePrefix || replaceTail)) {
      const color = forming.close >= forming.open ? "#74bda4" : "#f49b98";
      candleSeries.update({ ...datum(forming), color, wickColor: color, borderColor: color });
    }
    if (bars.length && !before.bars.length) {
      scale.fitContent();
    } else if (historicalView && (!samePrefix || replaceTail)) {
      scale.setVisibleLogicalRange(historicalView);
    }
    drawn.current = { bars, forming };
    reposition.current();
  }, [bars, forming]);

  useEffect(() => { reposition.current(); }, [marks, showSignals]);
  useEffect(() => {
    if (!series.current) return;
    if (realPrice === undefined) {
      if (line.current) { series.current.removePriceLine(line.current); line.current = null; }
      return;
    }
    const options = { price: realPrice, color: "#256b79", lineWidth: 1 as const, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: priceLabel };
    if (line.current) line.current.applyOptions(options);
    else line.current = series.current.createPriceLine(options);
  }, [realPrice, priceLabel]);

  const entry = levels?.entry, stop = levels?.stop_loss, target = levels?.target;
  useEffect(() => {
    const candles = series.current;
    if (!candles || !showSignals || entry === undefined || stop === undefined || target === undefined) return;
    const prices = [
      { price: entry, title: "Entry", color: "#385ab4" },
      { price: stop, title: "Stop", color: "#ad3047" },
      { price: target, title: "Target", color: "#187255" },
    ];
    const lines = prices.map(p => candles.createPriceLine({
      ...p, lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: true,
    }));
    return () => {
      if (candles === series.current) for (const item of lines) candles.removePriceLine(item);
    };
  }, [entry, stop, target, showSignals]);

  function zoom(factor: number) {
    const scale = api.current?.timeScale();
    const range = scale?.getVisibleLogicalRange();
    if (!scale || !range) return;
    const width = Math.max(8, Math.min(Math.max(20, bars.length + 5), (range.to - range.from) * factor));
    scale.setVisibleLogicalRange({ from: range.to - width, to: range.to });
  }

  return <div className="chart-board" ref={frame}>
    <div className="chart-tools">
      <div className="chart-type"><span aria-hidden="true" className="chart-candle-icon">╹╿</span>Heikin Ashi <span className="chart-faint">· 15m</span></div>
      <button className="chart-signal-toggle" aria-pressed={showSignals} onClick={() => setShowSignals(!showSignals)}>Signals</button>
      <div className="chart-nav">
        <button aria-label="Zoom out" title="Zoom out" onClick={() => zoom(1.35)}>−</button>
        <button aria-label="Zoom in" title="Zoom in" onClick={() => zoom(1 / 1.35)}>+</button>
        <button onClick={() => api.current?.timeScale().fitContent()} title="Show entire selected history">Fit</button>
        <button onClick={() => api.current?.timeScale().scrollToRealTime()} title="Go to latest candle">Latest</button>
        <button aria-label={full ? "Exit full screen" : "Full screen"} title="Full screen" onClick={() => {
          if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
          else void frame.current?.requestFullscreen?.().catch(() => {});
        }}>⛶</button>
      </div>
    </div>
    <div className="chart-values">
      <span>{selected ? formatStamp(selected.time) + " IST" : "OHLC"}</span>
      {selected && <div className={selected.close >= selected.open ? "chart-up" : "chart-down"}>
        {(["open", "high", "low", "close"] as const).map((k) => <span key={k}><i>{k[0].toUpperCase()}</i> {formatPrice(selected[k])}</span>)}
      </div>}
      {forming && (!hovered || hovered.time === forming.time) && <small>Forming</small>}
    </div>
    <div className="chart-plot" role="region" aria-label="Interactive 15-minute Heikin Ashi chart" data-range-size={rangeSize} data-closed-bars={bars.length} data-forming={!!forming}>
      <div className="chart-surface" ref={host} />
      <div className="chart-marks" ref={overlay}>{showSignals && marks.map((m) =>
        <span key={m.time} className={`chart-badge ${m.side.toLowerCase()}`} data-time={m.time} data-price={m.price} data-side={m.side}
          aria-label={`${m.side === "BUY" ? "Buy" : "Sell"} signal on ${formatStamp(m.time)} IST`}>{m.side === "BUY" ? "Buy" : "Sell"}</span>)}</div>
      {!last && <div className="chart-empty" role="status">{loading ? "Loading candles…" : "No completed candles in this range"}</div>}
    </div>
    <div className="chart-caption"><span>{bars.length} closed candles · {marks.length} confirmed {marks.length === 1 ? "signal" : "signals"} in history</span><span>NSE · IST (UTC+5:30)</span></div>
  </div>;
}
