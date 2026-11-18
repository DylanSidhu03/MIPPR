// Upload limits: everything runs on the user's machine, so a huge file would only exhaust the browser's
// memory (a 60-megapixel photo already needs about 1 GB while it is processed). Phone photos are 12-50 MP.
export const MAX_FILE_MB = 60;
export const MAX_MEGAPIXELS = 60;

/** An error message if the file is too large to process, else null. */
export function fileProblem(file) {
  if (!/^image\//.test(file.type || "image/")) return "This is not an image file.";
  if (file.size > MAX_FILE_MB * 1e6) return `The file is ${(file.size / 1e6).toFixed(0)} MB; the limit is ${MAX_FILE_MB} MB.`;
  return null;
}

/** An error message if the decoded photo is too large to process, else null. */
export function pixelProblem(width, height) {
  const mp = (width * height) / 1e6;
  return mp > MAX_MEGAPIXELS
    ? `The photo is ${mp.toFixed(0)} megapixels; the limit is ${MAX_MEGAPIXELS}. Use the camera's normal photo size.`
    : null;
}
