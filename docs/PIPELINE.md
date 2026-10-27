# MIPPR pipeline plan

Every action needed for the pipeline to work, in order. Check items off as they are finished (edit this file or use the linked issues).

## 1. Define scope and classes

**Goal:** Write down exactly what the pipeline decides, so every later step has a target.

**Flow:** Project guidelines -> Class definitions + size rule

- [ ] Fix the size cutoff (particles larger than 500 µm) and which dimension it applies to: longest axis or equivalent diameter
- [ ] List morphology classes (fragment, fiber, film, foam, pellet or bead) with a written visual rule and example photo for each
- [ ] List color classes (for example black, white/clear, blue, red, green, yellow, other) with reference swatches
- [ ] Decide how 'not plastic' particles are handled and what the output says when the model is unsure
- [ ] Choose the output table columns and units (µm, µm²) before any code exists

**In:** Lab sorting protocol, current hand-picking notes.  
**Out:** A one-page classification spec every annotator and script follows.  
**Watch for:** Hand-picking depends on who is looking. If the class rules stay vague, the labels and the model inherit that disagreement.

## 2. Standardize image capture

**Goal:** Make photos comparable across days, people and labs.

**Flow:** Physical samples -> Calibrated image set

- [ ] Pick the imaging setup (stereo microscope or fixed camera) and lock height, zoom and lighting
- [ ] Choose one background that separates every color class, including white and clear particles
- [ ] Place a scale reference and a color reference card in every frame
- [ ] Record pixels per µm for each setup and check it against a ruler image
- [ ] Set file naming and metadata (sample ID, date, operator, setup) and a folder layout
- [ ] Shoot a pilot batch of 50 to 100 particles covering every class

**In:** Filtered, dried samples; microscope or camera.  
**Out:** Images with a known scale and color reference, plus a metadata sheet.  
**Watch for:** Glare, shadows and clear particles on a bright background hide edges. Fixing this at capture is cheaper than fixing it in code.

## 3. Build the labeled dataset

**Goal:** Create the ground truth that both trains and judges the pipeline.

**Flow:** Pilot images -> Labeled masks + class tags

- [ ] Choose an annotation tool (CVAT, Label Studio or similar) and set it up with the class list
- [ ] Outline particles and tag color and morphology on at least 300 particles
- [ ] Have a second person label a 20% subset independently
- [ ] Measure agreement between labelers (Cohen's kappa for classes, overlap for outlines)
- [ ] Resolve disagreements and update the class spec from what you learn
- [ ] Split into train, validation and test sets by sample, not by image

**In:** Pilot images, class spec.  
**Out:** Versioned dataset with a held-out test set and a measured human agreement ceiling.  
**Watch for:** The model cannot beat the agreement between humans. Measure that number early so the accuracy target is realistic.

## 4. Preprocess images

**Goal:** Turn raw photos into consistent, calibrated images.

**Flow:** Raw images -> Normalized images

- [ ] Correct uneven illumination with a flat-field or background image
- [ ] Normalize white balance and color using the reference card
- [ ] Convert to a standard color space (LAB) for color work
- [ ] Read scale from metadata or detect the scale reference to get µm per pixel
- [ ] Write unit tests on a few known images

**In:** Raw images and metadata.  
**Out:** Normalized images and a µm-per-pixel value for each.  
**Watch for:** Color class accuracy depends on this step. A wrong white balance moves particles across color classes.

## 5. Segment particles

**Goal:** Find every particle and separate touching ones.

**Flow:** Normalized images -> Particle masks

- [ ] Build a classical baseline (threshold, morphology, watershed) and score it on the validation set
- [ ] Try a learned segmenter (Cellpose, SAM or a small U-Net) and compare against the baseline
- [ ] Handle touching and overlapping particles, and thin fibers that break into pieces
- [ ] Remove debris, dust and edge artifacts with area and shape rules
- [ ] Write out an overlay image of outlines on the photo for every input

**In:** Normalized images, labeled masks.  
**Out:** One mask per particle and a QC overlay image.  
**Watch for:** Fibers and clear particles are the usual failures. Look at failures by class, not only the average score.

## 6. Measure size and shape

**Goal:** Produce standardized numbers in µm.

**Flow:** Particle masks + scale -> Measurement table

- [ ] Compute area, equivalent diameter, longest and shortest axis (Feret), and aspect ratio
- [ ] Measure fiber length along the skeleton instead of the bounding box
- [ ] Convert pixels to µm and µm² with the stored scale
- [ ] Apply the 500 µm cutoff and flag particles within 10% of it for review
- [ ] Compare automated sizes with manual caliper or image-tool measurements on 50 particles

**In:** Masks, µm-per-pixel value.  
**Out:** One row per particle with size and shape columns.  
**Watch for:** A scale error shifts every particle across the 500 µm line, so check calibration before trusting counts.

## 7. Classify color and morphology

**Goal:** Replace the visual judgment call with a repeatable rule or model.

**Flow:** Masks + normalized image -> Color and morphology labels

- [ ] Extract mean and dominant color per particle in LAB, ignoring edge pixels
- [ ] Map color to classes with clustering or a small classifier trained on the labeled set
- [ ] Classify morphology from shape features (aspect ratio, solidity, skeleton length) with a baseline model
- [ ] Try a CNN on particle crops if the feature model falls short
- [ ] Output a confidence score and send low-confidence particles to a review list
- [ ] Decide how plastic versus non-plastic is flagged, and state plainly what the images cannot tell you (polymer type)

**In:** Masks, images, labeled dataset.  
**Out:** Color, morphology and confidence columns added to the table.  
**Watch for:** Images alone cannot confirm a particle is plastic. Keep a human review path and say so in the output.

## 8. Validate against people

**Goal:** Show the pipeline is good enough to trust, with numbers.

**Flow:** Test set + pipeline output -> Accuracy report

- [ ] Run the pipeline once on the held-out test set and do not tune on it
- [ ] Report detection recall and precision, class confusion matrices, and size error in µm
- [ ] Compare model-versus-human agreement with human-versus-human agreement
- [ ] Count how many particles land in the review list
- [ ] Time the manual workflow against the pipeline on the same batch
- [ ] Run a small test on images from a second setup or lab

**In:** Held-out test set, human agreement numbers from the dataset stage.  
**Out:** A short report with a pass or fail against targets set at the start.  
**Watch for:** A model that works only on the pilot setup is not a standardized method. The second-setup test shows whether it generalizes.

## 9. Batch run and outputs

**Goal:** Process a whole folder with one command and get tidy results.

**Flow:** Folder of images -> CSV + QC overlays + summary

- [ ] Wrap the stages into one command that takes a folder and a settings file
- [ ] Write per-particle CSV, per-sample summary counts, and QC overlays
- [ ] Log versions, settings and scale used for every run so results can be reproduced
- [ ] Handle bad inputs (missing scale, blurry image) with a clear message instead of a crash
- [ ] Time it on 500 images and fix the slowest step
- [ ] Write a README with install steps and a worked example

**In:** Image folder, settings file.  
**Out:** A command-line tool that others in the lab can run.  
**Watch for:** If it is hard to install, nobody outside the project will use it.

## Decision point: build the web app?

Go only if validation met its targets, the batch tool runs for someone other than you, and there is a hosting and maintenance plan. Otherwise release the command-line tool and documentation as the finished project.

- [ ] Validation targets met
- [ ] A second person ran the batch tool without help
- [ ] Hosting and upkeep plan agreed

## 10. Open-source web app (if feasible)

**Goal:** Let researchers and community scientists use the pipeline in a browser.

**Flow:** Uploaded images -> Downloadable results

- [ ] Sketch the screens: upload, set scale, run, review, export
- [ ] Wrap the pipeline in a service with a job queue for batches
- [ ] Build the upload and progress screens, and a results table with overlays
- [ ] Add a review screen where a person can correct a class or outline and the correction is saved
- [ ] Support scale entry for users without a reference card, with clear guidance on how to take the photo
- [ ] Export CSV and a PDF or HTML summary
- [ ] Choose a license, add contribution notes and tests, and set up automated builds
- [ ] Pick hosting, set upload size limits and a data retention policy
- [ ] Pilot with two or three outside users and collect what confused them

**In:** Batch tool, accuracy report.  
**Out:** A hosted app and a public repository.  
**Watch for:** Community photos will vary far more than lab photos. Plan for quality checks on upload and for retraining with corrected labels.

## 11. Document and release (if feasible)

**Goal:** Make the method citable and reusable.

**Flow:** Everything above -> Public release

- [ ] Publish the labeled dataset or a sample, with a data card
- [ ] Write the methods page: class definitions, calibration, accuracy and known limits
- [ ] Tag version 1.0 with a changelog
- [ ] Draft a short paper or report and share the repository with the lab group
- [ ] Set a plan for who answers issues and retrains the model

**In:** Validated pipeline, documentation.  
**Out:** Tagged release and methods write-up.  
**Watch for:** Without stated limits, users will over-trust the output.

