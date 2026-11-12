// The pinned OpenCV.js build, and loading it in the browser.
// The file is the official docs.opencv.org/4.10.0/opencv.js build as redistributed in the npm package
// @techstark/opencv-js (which adds a one-line UMD patch). It includes ArUco (cv.aruco_ArucoDetector, DICT_4X4_50).
// Node (tests) loads the same file from web/vendor/, fetched by web/scripts/fetch_opencv.mjs.

export const OPENCV = Object.freeze({
  version: "4.10.0",
  npm: "@techstark/opencv-js@4.10.0-release.1",
  url: "https://cdn.jsdelivr.net/npm/@techstark/opencv-js@4.10.0-release.1/dist/opencv.js",
  tarball: "https://registry.npmjs.org/@techstark/opencv-js/-/opencv-js-4.10.0-release.1.tgz",
  sha256: "19b46167b59efbef9cc3836264b0b657110833e4b1df84282004b8b3141c048d",
  integrity: "sha384-XsTfGA62I8LzqS3D7IcgiSOCrJuECWLcg4s1M0AnrkDCcJ8lXX+j+qdg+o6t7KZa",
  vendorPath: "vendor/opencv-4.10.0.js", // relative to web/
});

/**
 * Resolve with `cv` once the OpenCV.js runtime is ready. In 4.x the module object has its own `then`,
 * which makes promises adopt it forever, so it is removed first.
 */
export function whenReady(mod) {
  if (mod instanceof Promise) return mod;
  return new Promise((resolve) => {
    const done = () => {
      delete mod.then;
      resolve(mod);
    };
    if (mod.Mat) done();
    else mod.onRuntimeInitialized = done;
  });
}

let loading = null;

/** Load OpenCV.js once in the browser with a classic script tag (the file is UMD, not an ES module). */
export function loadOpenCV({ src = OPENCV.url, integrity = OPENCV.integrity } = {}) {
  loading ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.async = true;
    if (integrity) {
      s.integrity = integrity;
      s.crossOrigin = "anonymous";
    }
    s.onload = () => whenReady(window.cv).then(resolve, reject);
    s.onerror = () => reject(new Error(`Could not load OpenCV.js from ${src}`));
    document.head.appendChild(s);
  });
  return loading;
}
