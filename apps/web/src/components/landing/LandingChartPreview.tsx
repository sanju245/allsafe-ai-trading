const closes = [32, 37, 34, 28, 31, 39, 46, 43, 55, 60, 66, 61, 69, 75, 72, 67, 56, 54, 58, 64, 62, 68, 77, 80, 76, 83, 79, 85];
const labels = { 6: "Buy", 16: "Sell" } as const;

export default function LandingChartPreview() {
  return (
    <figure className="landing-chart-preview" aria-label="Illustrative NIFTY 50 chart with sample Buy and Sell candle labels">
      <div className="landing-chart-header">
        <span className="landing-index-mark" aria-hidden="true">50</span>
        <div>
          <p className="font-semibold text-white">NIFTY 50</p>
          <p className="mt-0.5 text-xs text-slate-400">NSE · 15-minute candles</p>
        </div>
        <span className="as-pill landing-sample">Sample chart</span>
      </div>
      <div className="landing-chart-body">
        <div className="landing-chart-quote">
          <strong>25,392.40</strong>
          <span>+0.42%</span>
        </div>
        <div className="landing-chart-area" aria-hidden="true">
          <div className="landing-chart-grid">
            {closes.map((close, index) => {
              const open = index === 0 ? 25 : closes[index - 1];
              const lower = Math.min(open, close);
              const upper = Math.max(open, close);
              const low = lower - 4 - (index % 3);
              const high = upper + 4 + (index % 4);
              const label = index === 6 ? labels[6] : index === 16 ? labels[16] : undefined;
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
          <div className="landing-chart-axis"><span>25,420</span><span>25,360</span><span>25,300</span><span>25,240</span></div>
        </div>
        <div className="landing-chart-times" aria-hidden="true"><span>09:15</span><span>11:00</span><span>12:45</span><span>14:30</span></div>
      </div>
      <figcaption className="landing-chart-caption">
        <span className="as-led" aria-hidden="true" /> Labels on confirmed candles <span className="ml-auto text-slate-500">IST</span>
      </figcaption>
    </figure>
  );
}
