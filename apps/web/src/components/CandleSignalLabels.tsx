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
    return <text key={time} x={x(index)} y={buy ? y(candle.low) + 15 : y(candle.high) - 6}
      data-side={side} data-time={time} textAnchor="middle" fontSize="13" fontWeight="700"
      fill={buy ? "#6ee7b7" : "#fda4af"} stroke="#0b0f14" strokeWidth="3" paintOrder="stroke">
      <title>{side} signal on {formatStamp(time)} IST</title>{side}
    </text>;
  });
}
