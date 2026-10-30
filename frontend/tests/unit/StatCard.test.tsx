import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatCard } from "@/components/widgets/StatCard";

describe("StatCard", () => {
  it("renders label and value", () => {
    render(<StatCard label="Active Models" value="5/6" />);
    expect(screen.getByText("Active Models")).toBeInTheDocument();
    expect(screen.getByText("5/6")).toBeInTheDocument();
  });

  it("renders numeric values", () => {
    render(<StatCard label="External Connections" value={0} />);
    expect(screen.getByText("0")).toBeInTheDocument();
  });

  it("renders an optional hint", () => {
    render(<StatCard label="Active Models" value="5/6" hint="local runtime" />);
    expect(screen.getByText("local runtime")).toBeInTheDocument();
  });

  it("omits the hint element when not provided", () => {
    const { container } = render(<StatCard label="X" value="1" />);
    expect(container.textContent).not.toContain("undefined");
  });
});
