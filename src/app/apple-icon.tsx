import { ImageResponse } from "next/og";
import { AppMark } from "./icon";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(<AppMark px={size.width} />, size);
}
