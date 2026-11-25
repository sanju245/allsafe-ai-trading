import { epoch, formatStamp, type RawCandle, type Side, type Signal } from "@/lib/indexChart";

type Props = {
  candles: RawCandle[];
  signals: Signal[];
  x: (index: number) => number;
  y: (price: number) => number;
};

export default function CandleSignalLabels({ candles, signals, x, y }: Props) {
  const sides = new Map<number, Side>();
  for (const signal of signals) {
    if (signal.decision === "BUY" || signal.decision === "SELL") {
      sides.set(epoch(signal.timestamp), signal.decision);
    }
  }
  return candles.map((candle, index) => {
    const time = epoch(candle.timestamp);
    const side = sides.get(time);
    if (!side || candle.is_forming || candle.is_incomplete || candle.is_confirmed === false) return null;
    const buy = side === "BUY";
    const text = buy ? "Buy" : "Sell";
    const center = x(index);
    const wick = buy ? y(candle.low) : y(candle.high);
    const boxTop = buy ? wick + 5 : wick - 23;
    const fill = buy ? "#a9edb3" : "#ffc1c4";
    return (
      <g key={time} data-side={side} data-time={time}>
        <title>{text} signal on {formatStamp(time)} IST</title>
        <rect x={center - 17} y={boxTop} width="34" height="18" rx="4" fill={fill} />
        <path d={`M ${center - 4} ${buy ? boxTop : boxTop + 18} L ${center} ${buy ? wick + 1 : wick - 1} L ${center + 4} ${buy ? boxTop : boxTop + 18} Z`} fill={fill} />
        <text x={center} y={boxTop + 12.5} textAnchor="middle" fontSize="11.5" fontWeight="700" fill={buy ? "#143528" : "#521e27"}>{text}</text>
      </g>
    );
  });
}
