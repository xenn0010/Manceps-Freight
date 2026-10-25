import { cancelRender, continueRender, delayRender, staticFile } from "remotion";

const FAMILY = "Alliance No.2";
let started = false;

/** Load the app's Alliance No.2 face once and hold rendering until it is ready; abort the render if it fails. */
export function ensureFonts(): void {
  if (started || typeof document === "undefined") return;
  started = true;
  const handle = delayRender("Loading Alliance No.2");
  const face = new FontFace(FAMILY, `url(${staticFile("brand/AllianceNo2-Regular.otf")}) format("opentype")`);
  face
    .load()
    .then((f) => {
      document.fonts.add(f);
      continueRender(handle);
    })
    .catch((err: unknown) => cancelRender(err instanceof Error ? err : new Error(String(err))));
}
