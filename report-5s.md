# Video Segmentation Report

**Duration:** 783.3s | **Resolution:** 1920x1080 | **FPS:** 59.94 | **Segments:** 16

## Pipeline Configuration

| Parameter | Value |
|-----------|-------|
| Segmentation mode | `semantic` (LLM-based, from SRT transcript) |
| Segmentation model | `google/gemini-2.5-flash` via OpenRouter |
| Keyframe extraction | One frame every 5 seconds within each segment |
| VLM model | `google/gemini-2.5-flash` via OpenRouter |
| Subtitle source | Auto-detected `*.en-orig.srt` (YouTube auto-generated) |
| Time range | 0:00 - 11:00 (assembly portion only) |

### Step 1: SRT Semantic Segmentation Prompt (`srt2segment.py`)

SRT subtitles are merged into timestamped text blocks, then sent to the LLM with:

```
You are analyzing a transcript of a drone assembly tutorial video (0:00 to ~11:00).

Below is the timestamped transcript. Your task is to identify semantically coherent segments —
each segment should correspond to ONE assembly step or topic (e.g., "attach arms to frame",
"solder motor wires to ESC", "mount camera").

Rules:
- Each segment must have a clear start_sec and end_sec (in seconds, float).
- Segments must be contiguous and non-overlapping, covering the full transcript.
- Aim for 10-25 segments. Merge trivially short transitions into adjacent segments.
- Give each segment a short title (5-10 words) describing the assembly step.
- Output ONLY valid JSON array, no other text.
```

- **Input**: timestamped transcript text (no images)
- **Output**: JSON array of `{index, start_sec, end_sec, title}`

### Step 2: VLM Segment Description Prompt (`segment_video.py`)

For each segment, keyframe images (every 5s) + aligned SRT text are sent to the VLM:

```
These are keyframes from a video segment ({start}s - {end}s).
Narration during this segment: "{aligned_subtitle_text}"
Describe what is happening in this segment in 2-3 sentences.
Focus on the main action, objects shown, and any text visible on screen.
```

- **Input**: keyframe images (base64, all frames in segment) + time range + aligned SRT transcript
- **Output**: 2-3 sentence visual description per segment
- **Temperature**: 0.3 | **Max tokens**: 300

## Table of Contents

| Seg | Time | Duration | Title |
|-----|------|----------|-------|
| [0](#segment-0-000000---001008--introduction-to-the-quadcopter-build) | 00:00 - 00:10 | 10.1s | Introduction to the quadcopter build |
| [1](#segment-1-001008---003186--overview-of-all-drone-parts) | 00:10 - 00:31 | 21.8s | Overview of all drone parts |
| [2](#segment-2-003186---005223--assemble-frame-arms-to-base-plate) | 00:31 - 00:52 | 20.4s | Assemble frame arms to base plate |
| [3](#segment-3-005223---014333--tighten-frame-arms-and-prepare-motor-wires) | 00:52 - 01:43 | 51.1s | Tighten frame arms and prepare motor wires |
| [4](#segment-4-014333---021831--sleeve-motor-wires-for-protection) | 01:43 - 02:18 | 35.0s | Sleeve motor wires for protection |
| [5](#segment-5-021831---032015--mount-motors-to-arms-with-loctite) | 02:18 - 03:20 | 61.8s | Mount motors to arms with Loctite |
| [6](#segment-6-032015---034052--mount-4-in-1-esc-and-secure-stack) | 03:20 - 03:40 | 20.4s | Mount 4-in-1 ESC and secure stack |
| [7](#segment-7-034052---041340--solder-motor-wires-to-esc-pads) | 03:40 - 04:13 | 32.9s | Solder motor wires to ESC pads |
| [8](#segment-8-041340---052595--solder-power-lead-to-xt60-connector) | 04:13 - 05:25 | 72.6s | Solder power lead to XT60 connector |
| [9](#segment-9-052595---055685--solder-battery-lead-to-4-in-1-esc) | 05:25 - 05:56 | 30.9s | Solder battery lead to 4-in-1 ESC |
| [10](#segment-10-055685---065842--add-capacitor-to-esc-and-secure-wires) | 05:56 - 06:58 | 61.6s | Add capacitor to ESC and secure wires |
| [11](#segment-11-065842---073188--prepare-and-solder-receiver-wires) | 06:58 - 07:31 | 33.5s | Prepare and solder receiver wires |
| [12](#segment-12-073188---082271--connect-flight-controller-and-receiver) | 07:31 - 08:22 | 50.8s | Connect flight controller and receiver |
| [13](#segment-13-082271---085904--bind-receiver-to-transmitter) | 08:22 - 08:59 | 36.3s | Bind receiver to transmitter |
| [14](#segment-14-085904---101264--mount-receiver-and-antennas) | 08:59 - 10:12 | 73.6s | Mount receiver and antennas |
| [15](#segment-15-101264---110000--mount-and-wire-fpv-camera) | 10:12 - 11:00 | 47.4s | Mount and wire FPV camera |

---

## Segment 0 [00:00.00 - 00:10.08] — Introduction to the quadcopter build

<div style="overflow-x:auto;white-space:nowrap;padding:4px 0"><img src="keyframes/seg000_frame000000.jpg" height="120"> <img src="keyframes/seg000_frame000299.jpg" height="120"> <img src="keyframes/seg000_frame000598.jpg" height="120"></div>

**Visual:** In this video segment, the presenter introduces a quadcopter build. The first two images show the fully assembled quadcopter, a TBS Source One 6S freestyle FPV quad, being held and rotated to display its components, including blue propellers and a camera. The third image shows various parts laid out on a grid mat, including carbon fiber frame pieces, motors, and electronics, as the presenter holds up a frame component, preparing to demonstrate the build process.

<details><summary>Transcript</summary>

in this video I'm gonna show you how to build this quadcopter this is the TBS source one and this is a 6s freestyle fpv quad now let's have a look at the

</details>


## Segment 1 [00:10.08 - 00:31.86] — Overview of all drone parts

<div style="overflow-x:auto;white-space:nowrap;padding:4px 0"><img src="keyframes/seg001_frame000604.jpg" height="120"> <img src="keyframes/seg001_frame000903.jpg" height="120"> <img src="keyframes/seg001_frame001202.jpg" height="120"> <img src="keyframes/seg001_frame001501.jpg" height="120"> <img src="keyframes/seg001_frame001800.jpg" height="120"></div>

**Visual:** In this video segment, a person showcases the components for building an FPV quadcopter. They hold up various parts, including a carbon fiber frame, motors, a camera, a flight controller, an ESC, a video transmitter, and a receiver, describing each item as they present it. The components are laid out on a black grid mat, and the person's hands are visible as they interact with the parts.

<details><summary>Transcript</summary>

fpv quad now let's have a look at the parts first we've got the TBS source one frame is a 5 inch freestyle frame the Emax eco 22:07 1700 kv motors the foxier Aero mini pro the Holley broke accout a v2 flight controller and techo 32 4 and 1 ESC the TBS unified Pro HV and the fr Sky xm+ receiver now let's put this

</details>


## Segment 2 [00:31.86 - 00:52.23] — Assemble frame arms to base plate

<div style="overflow-x:auto;white-space:nowrap;padding:4px 0"><img src="keyframes/seg002_frame001909.jpg" height="120"> <img src="keyframes/seg002_frame002208.jpg" height="120"> <img src="keyframes/seg002_frame002507.jpg" height="120"> <img src="keyframes/seg002_frame002806.jpg" height="120"> <img src="keyframes/seg002_frame003105.jpg" height="120"></div>

**Visual:** In this segment, a person is assembling a drone frame, specifically the TBS Source One V3. They highlight that the arms of this version go under the base plate, providing more space for the stack. The person is shown attaching the carbon fiber arms to the main body of the drone frame, ensuring the pressed nuts point upwards.

<details><summary>Transcript</summary>

ESC the TBS unified Pro HV and the fr Sky xm+ receiver now let's put this thing together so this is the TPS source 1 v3 and the main difference between the v3 and the v2 is that the arms go under the base plate that way you've got more space for the stack so make sure you keep that in mind the pressed nuts point upward so you'll see those from the top

</details>


## Segment 3 [00:52.23 - 01:43.33] — Tighten frame arms and prepare motor wires

<div style="overflow-x:auto;white-space:nowrap;padding:4px 0"><img src="keyframes/seg003_frame003130.jpg" height="120"> <img src="keyframes/seg003_frame003429.jpg" height="120"> <img src="keyframes/seg003_frame003728.jpg" height="120"> <img src="keyframes/seg003_frame004027.jpg" height="120"> <img src="keyframes/seg003_frame004326.jpg" height="120"> <img src="keyframes/seg003_frame004625.jpg" height="120"> <img src="keyframes/seg003_frame004924.jpg" height="120"> <img src="keyframes/seg003_frame005223.jpg" height="120"> <img src="keyframes/seg003_frame005522.jpg" height="120"> <img src="keyframes/seg003_frame005821.jpg" height="120"> <img src="keyframes/seg003_frame006120.jpg" height="120"></div>

**Visual:** In this segment, a person assembles a drone frame and prepares the motors. They attach the carbon fiber arms to the main body of the drone, securing them with screws. The person then sleeves the motor wires with a purple paracord, explaining that this protects the wires and improves aesthetics. A small plastic bag with the text "FOR 4MM THICK ARMS" is also visible, likely containing screws or other small parts for the assembly.

<details><summary>Transcript</summary>

upward so you'll see those from the top and you use the longer screws in the middle for the stack so do one arm at a time but don't pet miss fuse down too much because you'll have a hard time getting all the other arms in there you just tighten it down when it's all put together like this next we'll do the motors and I like to sleeve my motor wires this is a para max it's a type of paracord and it's about a quarter inch so it's just enough to fit the 3 motor wires usually I'll spray the ends a little bit melt them down so that the wires will fit in there and it might take a little finagling to get them in but usually you can make it work this is entirely optional you can use some electrical tape or whatever you'd like to keep the wires down against the frame but I like this it looks nice and it protects the motor wires against prop strikes I think it's worth the extra few minutes it takes to do it so next we want to put the motors on the arms and

</details>


## Segment 4 [01:43.33 - 02:18.31] — Sleeve motor wires for protection

<div style="overflow-x:auto;white-space:nowrap;padding:4px 0"><img src="keyframes/seg004_frame006193.jpg" height="120"> <img src="keyframes/seg004_frame006492.jpg" height="120"> <img src="keyframes/seg004_frame006791.jpg" height="120"> <img src="keyframes/seg004_frame007090.jpg" height="120"> <img src="keyframes/seg004_frame007389.jpg" height="120"> <img src="keyframes/seg004_frame007688.jpg" height="120"> <img src="keyframes/seg004_frame007987.jpg" height="120"> <img src="keyframes/seg004_frame008286.jpg" height="120"></div>

**Visual:** The video segment shows a person assembling a drone. They begin by attaching motors to the drone's arms using screws, suggesting the use of blue Loctite to secure them. After the motors are in place, the person separates the flight controller from the 4-in-1 ESC, preparing to mount the ESC and solder the motors.

<details><summary>Transcript</summary>

minutes it takes to do it so next we want to put the motors on the arms and for this we want to use the screws four four millimeter arms which these are and you might want to use some blue lock types just to make sure that the screws won't wiggle loose that's optional but I usually like to recommend it okay now that the motors are in place we can work on the four and one ESC first you want to separate the flight controller from the foreign one so we can mount just the ESC and soldered the motors you might need to unscrew these so that the nylon standoffs of this can sit flush with the top of the bottom plates make sure that it's tight enough that the stack doesn't have any wiggle room we don't want any vibrations next

</details>


## Segment 5 [02:18.31 - 03:20.15] — Mount motors to arms with Loctite

<div style="overflow-x:auto;white-space:nowrap;padding:4px 0"><img src="keyframes/seg005_frame008290.jpg" height="120"> <img src="keyframes/seg005_frame008589.jpg" height="120"> <img src="keyframes/seg005_frame008888.jpg" height="120"> <img src="keyframes/seg005_frame009187.jpg" height="120"> <img src="keyframes/seg005_frame009486.jpg" height="120"> <img src="keyframes/seg005_frame009785.jpg" height="120"> <img src="keyframes/seg005_frame010084.jpg" height="120"> <img src="keyframes/seg005_frame010383.jpg" height="120"> <img src="keyframes/seg005_frame010682.jpg" height="120"> <img src="keyframes/seg005_frame010981.jpg" height="120"> <img src="keyframes/seg005_frame011280.jpg" height="120"> <img src="keyframes/seg005_frame011579.jpg" height="120"> <img src="keyframes/seg005_frame011878.jpg" height="120"></div>

**Visual:** In this segment, a person is assembling a drone. They begin by securing components to the carbon fiber frame with screws using an electric screwdriver. The main action then shifts to soldering, where the person applies liquid soldering flux to the pads of an electronic speed controller (ESC) mounted on the drone frame, then solders wires from the motors to the ESC. Finally, they solder wires to an XT60 connector, using blue tack to hold the connector in place.

<details><summary>Transcript</summary>

that the stack doesn't have any wiggle room we don't want any vibrations next remove the nylon standoffs from the side that you're gonna be soldering first I like to use this liquid soldering flux it works really well to prepare the pads and even to smooth out some solder so you want to feel the entire pad and these pads are a little long so you might need to kind of push the solder back a little bit just to make sure that you fully cover the pad just be careful not to make your solder balls too tall because they'll overflow into one another now when it comes to soldering the wires I like to start from the right and work my way to the left most people have a hard time with this part of the build but it's really not too bad you just need to be real generous with the soldering flux and be careful not to push the wire down into the solder too quickly or it'll overflow into the next pad next let's do the power lead here I use some 16 gauge wire and it's really helpful to have some blue tech that way you can hold the xt60 down while you get the wires soldered up the trick here is not to fill the xc60 with too much solder but just enough so that when you push the wire in it doesn't overflow

</details>


## Segment 6 [03:20.15 - 03:40.52] — Mount 4-in-1 ESC and secure stack

<div style="overflow-x:auto;white-space:nowrap;padding:4px 0"><img src="keyframes/seg006_frame011997.jpg" height="120"> <img src="keyframes/seg006_frame012296.jpg" height="120"> <img src="keyframes/seg006_frame012595.jpg" height="120"> <img src="keyframes/seg006_frame012894.jpg" height="120"> <img src="keyframes/seg006_frame013193.jpg" height="120"></div>

**Visual:** In this segment, a person is shown preparing and soldering a battery lead to an electronic speed controller (ESC) on what appears to be a drone frame. They first apply heat shrink tubing to the wires of the battery lead, then strip the ends of the wires. Finally, they solder the prepared wires to the designated pads on the ESC, which is mounted on a carbon fiber frame.

<details><summary>Transcript</summary>

solder but just enough so that when you push the wire in it doesn't overflow after you've got that done just put some shrink tube over there and you're all set next we want to solder the battery lead to the foreign one ESC and we've got a couple solder pads here which you want to apply a generous amount of slot or two and these have these little kind of grooves here for the wire but I found

</details>


## Segment 7 [03:40.52 - 04:13.40] — Solder motor wires to ESC pads

<div style="overflow-x:auto;white-space:nowrap;padding:4px 0"><img src="keyframes/seg007_frame013217.jpg" height="120"> <img src="keyframes/seg007_frame013516.jpg" height="120"> <img src="keyframes/seg007_frame013815.jpg" height="120"> <img src="keyframes/seg007_frame014114.jpg" height="120"> <img src="keyframes/seg007_frame014413.jpg" height="120"> <img src="keyframes/seg007_frame014712.jpg" height="120"> <img src="keyframes/seg007_frame015011.jpg" height="120"></div>

**Visual:** In this segment, a person is shown soldering components onto a drone frame. They begin by soldering a black wire with a connector to a pad on the drone's circuit board, using a soldering iron and adding solder. Subsequently, they prepare to attach a capacitor, ensuring correct polarity by identifying the negative and positive sides, and then trim its leads before positioning it for soldering.

<details><summary>Transcript</summary>

or two and these have these little kind of grooves here for the wire but I found a little easier to start it to the top of the pads and you want the battery lead to go out through the side of the kwant rather than the back so you'll have to have one wire just a little shorter than the other and you might need to add a little slaughter just to get a nice clean joint here now let's add the capacitor this is the negative side and this is the positive side make sure you get the polarity correct you can just trim this down a little bit and it's really helpful to use a little bit of blue tech that hold it in place that way you can just add a little slaughter to

</details>


## Segment 8 [04:13.40 - 05:25.95] — Solder power lead to XT60 connector

<div style="overflow-x:auto;white-space:nowrap;padding:4px 0"><img src="keyframes/seg008_frame015188.jpg" height="120"> <img src="keyframes/seg008_frame015487.jpg" height="120"> <img src="keyframes/seg008_frame015786.jpg" height="120"> <img src="keyframes/seg008_frame016085.jpg" height="120"> <img src="keyframes/seg008_frame016384.jpg" height="120"> <img src="keyframes/seg008_frame016683.jpg" height="120"> <img src="keyframes/seg008_frame016982.jpg" height="120"> <img src="keyframes/seg008_frame017281.jpg" height="120"> <img src="keyframes/seg008_frame017580.jpg" height="120"> <img src="keyframes/seg008_frame017879.jpg" height="120"> <img src="keyframes/seg008_frame018178.jpg" height="120"> <img src="keyframes/seg008_frame018477.jpg" height="120"> <img src="keyframes/seg008_frame018776.jpg" height="120"> <img src="keyframes/seg008_frame019075.jpg" height="120"> <img src="keyframes/seg008_frame019374.jpg" height="120"></div>

**Visual:** The video segment shows the process of soldering components onto a drone frame. Initially, a capacitor is soldered to the ESC (Electronic Speed Controller) on the drone frame. Subsequently, a receiver (FrSky XM+) is prepared by soldering wires to it, and then it is connected and soldered to the flight controller, which is also mounted on the drone frame. Finally, the builder attempts to bind the receiver to a remote control, using tweezers to hold down the bind button.

<details><summary>Transcript</summary>

blue tech that hold it in place that way you can just add a little slaughter to the existing joints to hold it in place so that completes the motors and the four and one ESC next we'll just melt the heat shrink to secure the wires and we can move onto the receiver so here I'm using the fr sky XM plus which is a fairly economical and small receiver first we need some wire and I borrowed some from the camera there's more than enough to go around so we want to solder the SBUs five volt and ground wires to the XM plus again it's really handy to have some blue tech to hold it in place and it's usually a good idea to give your wires a little tug at the end to make sure they've got a solid connection to the board so next let's get the flight controller and plug it back in to the four and one ESC tuck that wire in and secure it with some nylon nuts now we can solder the receiver to the flight controller the S bus wire sliders to the r3 pad and the v Bolton ground solder to the v Bolton ground pads now at this point I like to bind to the receiver because once you've tucked it away inside the build it's really hard to get to the bind button so we might as well do that now I find it really difficult to plug the battery in while holding the bind button so I like to use tweezers in a clamp to hold it down for me it works really well and I can

</details>


## Segment 9 [05:25.95 - 05:56.85] — Solder battery lead to 4-in-1 ESC

<div style="overflow-x:auto;white-space:nowrap;padding:4px 0"><img src="keyframes/seg009_frame019537.jpg" height="120"> <img src="keyframes/seg009_frame019836.jpg" height="120"> <img src="keyframes/seg009_frame020135.jpg" height="120"> <img src="keyframes/seg009_frame020434.jpg" height="120"> <img src="keyframes/seg009_frame020733.jpg" height="120"> <img src="keyframes/seg009_frame021032.jpg" height="120"> <img src="keyframes/seg009_frame021331.jpg" height="120"></div>

**Visual:** In this video segment, a person is working on assembling a drone. They are shown holding a blue remote control with a screen displaying "FRSKY" and various settings like "Mode," "Range," and "E.Failsafe." The person then proceeds to connect and secure the receiver to the drone's frame, using heat shrink tubing to isolate it from other components. The drone's frame, flight controller, and ESC are visible on a black grid mat, along with various tools and screws.

<details><summary>Transcript</summary>

tweezers in a clamp to hold it down for me it works really well and I can usually get a bind on the first try let's just double check make sure that we're bound and we can tuck the receiver away now you want to isolate the receiver from the other components with a little bit of shrink tube just melt it a little bit so that you can remove it later in case you need to rebind and usually I'll tuck it between the flight controller and the foreign one ESC but there's plenty of room on this frame so I just kind of mounted it right in front of the two boards now ideally you want

</details>


## Segment 10 [05:56.85 - 06:58.42] — Add capacitor to ESC and secure wires

<div style="overflow-x:auto;white-space:nowrap;padding:4px 0"><img src="keyframes/seg010_frame021389.jpg" height="120"> <img src="keyframes/seg010_frame021688.jpg" height="120"> <img src="keyframes/seg010_frame021987.jpg" height="120"> <img src="keyframes/seg010_frame022286.jpg" height="120"> <img src="keyframes/seg010_frame022585.jpg" height="120"> <img src="keyframes/seg010_frame022884.jpg" height="120"> <img src="keyframes/seg010_frame023183.jpg" height="120"> <img src="keyframes/seg010_frame023482.jpg" height="120"> <img src="keyframes/seg010_frame023781.jpg" height="120"> <img src="keyframes/seg010_frame024080.jpg" height="120"> <img src="keyframes/seg010_frame024379.jpg" height="120"> <img src="keyframes/seg010_frame024678.jpg" height="120"> <img src="keyframes/seg010_frame024977.jpg" height="120"></div>

**Visual:** In this video segment, a person is assembling a drone. They begin by securing the receiver antennas to the front arms of the drone's frame using zip ties and heat shrink tubing, ensuring the antenna tips are protected. Next, they attach a blue "Foxeer" camera to the drone's frame using a bracket, carefully tightening screws and connecting the camera's wires to the flight controller, including soldering the 5V, video, and ground wires.

<details><summary>Transcript</summary>

I just kind of mounted it right in front of the two boards now ideally you want the receiver antennas to be at about a ninety degree angle from one another so I'd like to mount them two zip ties on the front two arms we have a little bit of shrink tube to hold it in place just make sure you cover the tips of the antennas because that's the most delicate part and that's where the transmission is received now let's mount the camera so you need to use this little bracket because this is a mini sized camera and this frame needs a full size camera just don't tuck these screws down too hard because I've correct the plastic before next you want to map the camera to the side plates don't tighten these screws down all the way because you're going to need to work with them to make sure it fits the slots in the on the top of the frame also be careful that you don't pinch your antenna wires when you put it down you can remove the purple wire because we're not using the camera OSD that's for relaying the voltage of the battery to the camera but we want to disable that will use the OSD on the flight controller so solder the three wires we've got five volts video and ground but these kind of pads it

</details>


## Segment 11 [06:58.42 - 07:31.88] — Prepare and solder receiver wires

<div style="overflow-x:auto;white-space:nowrap;padding:4px 0"><img src="keyframes/seg011_frame025080.jpg" height="120"> <img src="keyframes/seg011_frame025379.jpg" height="120"> <img src="keyframes/seg011_frame025678.jpg" height="120"> <img src="keyframes/seg011_frame025977.jpg" height="120"> <img src="keyframes/seg011_frame026276.jpg" height="120"> <img src="keyframes/seg011_frame026575.jpg" height="120"> <img src="keyframes/seg011_frame026874.jpg" height="120"></div>

**Visual:** The video segment shows the process of soldering wires to a drone's flight controller and then preparing a VTX (Video Transmitter) for installation. Initially, a person uses tweezers and a soldering iron to connect three wires (5V, video, and ground) from a camera to the flight controller, ensuring solid joints. Subsequently, the person prepares the VTX by removing unnecessary wires (5V, ground, and audio) from its connector, leaving only four wires for voltage in, ground, video, and smart audio. The VTX is identified as a "UNIFY PRO 5G8 HV" model.

<details><summary>Transcript</summary>

three wires we've got five volts video and ground but these kind of pads it works well just to add a little ball of solder and jab the ball of solder with the wire make sure you've got solid joints and you can tuck those wires away you're done with the camera so next let's move on to the V T X here we don't need a few of the wires we're not sending power from the V T X to the camera so we can remove the five volt and ground there and we're also not gonna use a microphone so you can remove the audio so that just leaves us with four wires we've got voltage in ground video and smart audio so we're gonna run the V T X by the B plus pad and this is basically just the battery voltage it's

</details>


## Segment 12 [07:31.88 - 08:22.71] — Connect flight controller and receiver

<div style="overflow-x:auto;white-space:nowrap;padding:4px 0"><img src="keyframes/seg012_frame027085.jpg" height="120"> <img src="keyframes/seg012_frame027384.jpg" height="120"> <img src="keyframes/seg012_frame027683.jpg" height="120"> <img src="keyframes/seg012_frame027982.jpg" height="120"> <img src="keyframes/seg012_frame028281.jpg" height="120"> <img src="keyframes/seg012_frame028580.jpg" height="120"> <img src="keyframes/seg012_frame028879.jpg" height="120"> <img src="keyframes/seg012_frame029178.jpg" height="120"> <img src="keyframes/seg012_frame029477.jpg" height="120"> <img src="keyframes/seg012_frame029776.jpg" height="120"> <img src="keyframes/seg012_frame030075.jpg" height="120"></div>

**Visual:** In this video segment, a person is shown soldering wires onto a drone's flight controller, specifically connecting the VTX (Video Transmitter) to the B+ pad for battery voltage and the smart audio wire to the TX6 pad for controlling video settings. They then twist the wires to keep them tidy and attach the VTX to the drone's frame using double-sided tape. Finally, the person adds standoffs to the top plate of the drone and secures the battery lead with a zip tie, completing the assembly process.

<details><summary>Transcript</summary>

the V T X by the B plus pad and this is basically just the battery voltage it's not regulated it's just the full voltage from the battery but this VTX can take up to six s so that'll be fine also we're gonna solder the smart patio wire to the TX six pad and we'll just configure that in beta flight this is for controlling the video frequency band channel and power output over the OSD in your goggles we can just twist the wires up a little bit here to keep things nice and tidy and we just need to add some double-sided tape to the bottom of the frame to hold the btx in place now that we're done with all the soldering let's finish this thing up so you want to add all the standoffs to all the top plate make sure you get these screws nice and tight because I've had them vibrate loose before next let's secure the battery lead to the standoff you just want to use a little zip tie here to hold it in place this is helpful because sometimes your battery might get ejected and you don't want it to tug at your

</details>


## Segment 13 [08:22.71 - 08:59.04] — Bind receiver to transmitter

<div style="overflow-x:auto;white-space:nowrap;padding:4px 0"><img src="keyframes/seg013_frame030132.jpg" height="120"> <img src="keyframes/seg013_frame030431.jpg" height="120"> <img src="keyframes/seg013_frame030730.jpg" height="120"> <img src="keyframes/seg013_frame031029.jpg" height="120"> <img src="keyframes/seg013_frame031328.jpg" height="120"> <img src="keyframes/seg013_frame031627.jpg" height="120"> <img src="keyframes/seg013_frame031926.jpg" height="120"> <img src="keyframes/seg013_frame032225.jpg" height="120"></div>

**Visual:** In this segment, a person is assembling a drone. They attach the top plate of the drone, securing it with screws and blue countersunk washers. Finally, they mount the antenna, tucking the pigtail underneath and securing it with a zip tie, before preparing to configure the camera.

<details><summary>Transcript</summary>

sometimes your battery might get ejected and you don't want it to tug at your stack now we can add the top plate now you might either loosen the screws on these side plates a little bit just to make it fit and once you've done that you can start screwing it in now I like to use these countersunk washers they add a nice little touch of color and they give you a nice flat surface to work with for your battery in your battery pan I had to cut the battery pad to make room for them but I think it turned out pretty nice now we can mount the antenna just scrunch that pigtail in under there and zip tie it to the top plate just like this and finally we just need to configure the camera so the camera comes with this little button pad and this is

</details>


## Segment 14 [08:59.04 - 10:12.64] — Mount receiver and antennas

<div style="overflow-x:auto;white-space:nowrap;padding:4px 0"><img src="keyframes/seg014_frame032310.jpg" height="120"> <img src="keyframes/seg014_frame032609.jpg" height="120"> <img src="keyframes/seg014_frame032908.jpg" height="120"> <img src="keyframes/seg014_frame033207.jpg" height="120"> <img src="keyframes/seg014_frame033506.jpg" height="120"> <img src="keyframes/seg014_frame033805.jpg" height="120"> <img src="keyframes/seg014_frame034104.jpg" height="120"> <img src="keyframes/seg014_frame034403.jpg" height="120"> <img src="keyframes/seg014_frame034702.jpg" height="120"> <img src="keyframes/seg014_frame035001.jpg" height="120"> <img src="keyframes/seg014_frame035300.jpg" height="120"> <img src="keyframes/seg014_frame035599.jpg" height="120"> <img src="keyframes/seg014_frame035898.jpg" height="120"> <img src="keyframes/seg014_frame036197.jpg" height="120"> <img src="keyframes/seg014_frame036496.jpg" height="120"></div>

**Visual:** The user is configuring the camera for a drone. They connect a small camera to a portable display, which shows "FXT TECHNOLOGY" and then "BETAFLIGHT" with an OSD (On-Screen Display) menu. The user navigates the menu to disable the OSD elements like name and voltage, and then proceeds to attach battery straps to the drone, secure motor wires with zip ties, and add a sticky pad for a camera mount.

<details><summary>Transcript</summary>

configure the camera so the camera comes with this little button pad and this is used to configure the settings so what we need to do is plug in our battery and get our fpv feed I've got a little portable display here and what you want to do is disable the OSD so you'll hold the top button for a couple seconds until the menu pops up and let's turn everything off because we don't want the name or the voltage or any of these things showing up we can use the beta flight OSD for all of this and in case you want to change any other settings you press the center button and you can change the color brightness or anything like that but usually I just keep the stock settings so for a frame like this I usually like to use a pair of battery straps and when you put them in you always want to have the fuzzy side down so the labelled side goes up let's just get those set and now we can secure the motor wires now you always want to secure these with some zip ties just in case a tree branch or something might snag the wires that way they're not going anywhere finally let's add a sticky pad for the camera mount here I'm gonna mount a GoPro Hero 7 and you want something like this because the mount will tend to scooch around even though you're attaching with zip ties I do like to use a good pair of strong zip ties here because they do tend to break in a crash

</details>


## Segment 15 [10:12.64 - 11:00.00] — Mount and wire FPV camera

<div style="overflow-x:auto;white-space:nowrap;padding:4px 0"><img src="keyframes/seg015_frame036721.jpg" height="120"> <img src="keyframes/seg015_frame037020.jpg" height="120"> <img src="keyframes/seg015_frame037319.jpg" height="120"> <img src="keyframes/seg015_frame037618.jpg" height="120"> <img src="keyframes/seg015_frame037917.jpg" height="120"> <img src="keyframes/seg015_frame038216.jpg" height="120"> <img src="keyframes/seg015_frame038515.jpg" height="120"> <img src="keyframes/seg015_frame038814.jpg" height="120"> <img src="keyframes/seg015_frame039113.jpg" height="120"> <img src="keyframes/seg015_frame039412.jpg" height="120"></div>

**Visual:** The video segment shows a person assembling and preparing a drone for flight. They use zip ties to secure a GoPro camera to the drone, then attach the propellers. The drone, with a 6S battery and GoPro Hero 7 Black, is weighed on a digital scale, showing "715" grams. The segment ends with a first-person view from the drone flying over a grassy area with trees and a playground.

<details><summary>Transcript</summary>

a good pair of strong zip ties here because they do tend to break in a crash and you really don't want to lose your GoPro so here it is the finished product I've got everything configured and ready to go here as far as the configuration is concerned you do need to plug this into your computer and set it up I've written a detailed guide which you can find on River builds comm the link is in the description and that will walk you through step by step how to configure this on your computer so let's check the final weigh-in and we're at 750 grams all up and this is with a 6 s battery and a GoPro Hero 7 black that's okay not the lightest but not the heaviest so let's check out the maiden flight I made some minor adjustments to the tune because this is a 6 s rig and

</details>

