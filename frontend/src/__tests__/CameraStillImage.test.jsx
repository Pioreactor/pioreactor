import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import CameraStillImage from "../components/CameraStillImage";

test("maps a loaded grayscale image to Magma and restores the original when disabled", () => {
  const pixels = new Uint8ClampedArray([0, 0, 0, 255, 128, 128, 128, 255, 255, 255, 255, 255]);
  const context = {
    drawImage: jest.fn(),
    getImageData: jest.fn(() => ({ data: pixels })),
    putImageData: jest.fn(),
  };
  const getContext = jest.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context);
  const { container, rerender } = render(<CameraStillImage src="/photo.jpg" alt="Camera snapshot" magma={false} />);
  const image = screen.getByRole("img", { name: "Camera snapshot" });
  Object.defineProperties(image, {
    complete: { value: true },
    naturalWidth: { value: 3 },
    naturalHeight: { value: 1 },
  });
  expect(container.querySelector("canvas")).toBeNull();

  rerender(<CameraStillImage src="/photo.jpg" alt="Camera snapshot" magma />);
  expect(Array.from(pixels)).toEqual([0, 0, 4, 255, 183, 55, 121, 255, 252, 253, 191, 255]);
  expect(context.putImageData).toHaveBeenCalledTimes(1);

  // Images arriving after the switch is enabled must also be transformed.
  fireEvent.load(image);
  expect(context.putImageData).toHaveBeenCalledTimes(2);
  rerender(<CameraStillImage src="/photo.jpg" alt="Camera snapshot" magma={false} />);
  expect(container.querySelector("canvas")).toBeNull();
  expect(image).toHaveAttribute("src", "/photo.jpg");
  getContext.mockRestore();
});
