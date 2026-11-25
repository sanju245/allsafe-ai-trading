import { useState } from "react";

const samples = {
  "NIFTY 50": {
    closes: [32, 37, 34, 28, 31, 39, 46, 43, 55, 60, 66, 61, 69, 75, 72, 67, 56, 54, 58, 64, 62, 68, 77, 80, 76, 83, 79, 85],
    price: "25,392.40", move: "+0.42%", scale: ["25,420", "25,360", "25,300", "25,240"], buy: 6, sell: 16,
  },
  "BANK NIFTY": {
    closes: [71, 66, 73, 78, 75, 68, 59, 64, 55, 47, 50, 42, 36, 30, 38, 43, 54, 51, 61, 66, 59, 57, 60, 55, 58, 63, 67, 65],
    price: "63,012.70", move: "−0.18%", scale: ["63,240", "63,080", "62,920", "62,760"], buy: 16, sell: 6,
  },
} as const;
type SampleIndex = keyof typeof samples;

export default function LandingChartPreview() {
  const [indexName, setIndexName] = useState<SampleIndex>("NIFTY 50");
  const { closes, price, move, scale, buy, sell } = samples[indexName];
  return (
    <figure className="landing-chart-preview" aria-label={`Illustrative ${indexName} chart with sample Buy and Sell candle labels`}>
      <div className="landing-chart-header">
        <div className="landing-chart-tabs" role="group" aria-label="Choose an example index">
          {(["NIFTY 50", "BANK NIFTY"] as const).map(name => (
            <button type="button" key={name} aria-pressed={indexName === name} onClick={() => setIndexName(name)}>{name}</button>
          ))}
        </div>
        <span className="as-pill landing-sample">Sample chart</span>
      </div>
      <div className="landing-chart-body">
        <div className="landing-chart-quote">
          <strong>{price}</strong>
          <span className={move.startsWith("−") ? "sample-down" : undefined}>{move}</span>
        </div>
        <div className="landing-chart-area" aria-hidden="true">
          <div className="landing-chart-grid">
            {closes.map((close, index) => {
              const open = index === 0 ? close - 7 : closes[index - 1];
              const lower = Math.min(open, close);
              const upper = Math.max(open, close);
              const low = lower - 4 - (index % 3);
              const high = upper + 4 + (index % 4);
              const label = index === buy ? "Buy" : index === sell ? "Sell" : undefined;
              return (
                <div className={close >= open ? "landing-up-candle" : "landing-down-candle"} key={index}>
                  <i className="landing-candle-wick" style={{ bottom: `${low}%`, height: `${high - low}%` }} />
                  <i className="landing-candle-body" style={{ bottom: `${lower}%`, height: `${upper - lower}%` }} />
                  {label && (
                    <span className={`landing-chart-marker ${label === "Buy" ? "is-buy" : "is-sell"}`} style={{ bottom: `${label === "Buy" ? low : high}%` }}>{label}</span>
                  )}
                </div>
              );
            })}
          </div>
          <div className="landing-chart-axis">{scale.map(value => <span key={value}>{value}</span>)}</div>
        </div>
        <div className="landing-chart-times" aria-hidden="true"><span>09:15</span><span>11:00</span><span>12:45</span><span>14:30</span></div>
      </div>
      <figcaption className="landing-chart-caption">
        <span className="as-led" aria-hidden="true" /> Labels on confirmed candles <span className="landing-chart-meta ml-auto">15 min · IST</span>
      </figcaption>
    </figure>
  );
}
