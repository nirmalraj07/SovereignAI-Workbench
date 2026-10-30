import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MetricGauge } from "@/components/widgets/MetricGauge";

describe("MetricGauge", () => {
  it("renders the label and formatted value", () => {
    render(<MetricGauge label="CPU Usage" value={42.567} />);
    expect(screen.getByText("CPU Usage")).toBeInTheDocument();
    expect(screen.getByText("42.6%")).toBeInTheDocument();
  });

  it("supports a custom unit", () => {
    render(<MetricGauge label="Queue depth" value={12} unit=" jobs" />);
    expect(screen.getByText("12.0 jobs")).toBeInTheDocument();
  });

  it("clamps the bar width to 100% for out-of-range values", () => {
    const { container } = render(<MetricGauge label="Overloaded" value={150} />);
    const bar = container.querySelector("div[style]");
    expect(bar).toHaveStyle({ width: "100%" });
  });

  it("clamps the bar width to 0% for negative values", () => {
    const { container } = render(<MetricGauge label="Underflow" value={-10} />);
    const bar = container.querySelector("div[style]");
    expect(bar).toHaveStyle({ width: "0%" });
  });
});
