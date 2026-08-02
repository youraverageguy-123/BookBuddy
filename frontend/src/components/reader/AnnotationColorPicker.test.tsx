import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AnnotationColorPicker } from "./AnnotationColorPicker";

describe("AnnotationColorPicker", () => {
  it("offers presets, a custom color input, and applies the chosen style", () => {
    const onColorChange = vi.fn();
    const onSave = vi.fn();
    render(<AnnotationColorPicker type="highlight" color="#f6c85f" x={400} y={200} saving={false} onColorChange={onColorChange} onSave={onSave} onCancel={vi.fn()}/>);

    expect(screen.getByRole("dialog", { name: "Highlight color" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Green" }));
    expect(onColorChange).toHaveBeenCalledWith("#6ecb8b");
    fireEvent.change(screen.getByLabelText("Choose any color"), { target: { value: "#123456" } });
    expect(onColorChange).toHaveBeenCalledWith("#123456");
    fireEvent.click(screen.getByRole("button", { name: "Apply highlight" }));
    expect(onSave).toHaveBeenCalledOnce();
  });
});
