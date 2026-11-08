# V5 ANIMATION CAPABILITY MATRIX
## UNIVERSAL ACTION LIBRARY & STATE MACHINE SPECIFICATION
**VERSION:** V5.0.0  
**ENGINE COMPONENT:** `motioncanvas/components/UniversalCharacterEngine.ts`

---

## 1. ACTION FAMILIES & CAPABILITY MATRIX

The V5 engine provides 32 core data-driven action primitives categorized into four functional families:

### 1.1 Locomotion Actions
| Action Identifier | Kinematic Mechanism | Foot-Locking | Torso Lean | Arm Coordination |
| :--- | :--- | :--- | :--- | :--- |
| **`idle`** | Sinusoidal respiratory cycle (1.8 rad/s) | Active (`y = 0`) | $0.00$ | Symmetric natural hang at hips |
| **`walk`** | 2-Phase harmonic stride (6.5 rad/s) | Alternating | $+0.08$ | Anti-phase pendulum swing |
| **`run`** | Dynamic flight & contact cycle (10.0 rad/s) | Flight phase | $+0.18$ | High elbow pump |
| **`sprint`** | High-energy athletic cycle (14.0 rad/s) | Flight phase | $+0.30$ | Full stroke forearm flexion |
| **`stop`** | Deceleration bracing & counter-lean | Dual-planted | $-0.15$ | Forward counterbalance reach |
| **`turn`** | Pivot rotation with head-lead anticipatory gaze | Ground pivot | Adaptive | Inward arm tuck |
| **`climb`** | Vertical 4-point alternating progression | Ledge-locked | $+0.15$ | Overhead reach & hoist |
| **`jump`** | Parabolic ballistic arc with aerial compression | Airborne | $+0.12$ | Upward thrust follow-through |

### 1.2 Interaction Actions
| Action Identifier | Kinematic Mechanism | Constraint Target | Hand State | Handedness |
| :--- | :--- | :--- | :--- | :--- |
| **`reach`** | Forward arm extension toward target coordinate | Target object `(x, y)` | Open / Pre-grasp | Left / Right |
| **`grab`** | High-tension finger curling around object anchor | Prop handle | Tight grip closure | Primary hand |
| **`hold`** | Isometric load stabilization near chest/hip | Attached object | Form-fit grip | Single / Dual |
| **`carry`** | Dynamic gait-coupled prop oscillation | Mobile object | Clamped | Primary hand |
| **`give`** | Two-handed or single forward extension | Receiving actor | Open presentation | Dual-handed |
| **`receive`** | Anticipatory palm upward cradle | Inbound prop | Cup / Cradle | Dual-handed |
| **`open`** | Bi-manual separation (e.g. scroll unrolling) | Prop endpoints | Pinch + Spread | Dual-handed |
| **`close`** | Inward folding or lid closure | Hinge anchor | Compress | Single / Dual |
| **`read`** | Downward eyeline tracking + elevated prop holding | Parchment/Tablet | Stabilized | Single / Dual |
| **`write`** | Micro-strokes on surface coordinate | Pen / Stylus | Precision pinch | Primary hand |
| **`point`** | Extended index finger with aligned eyeline | Interest vector | Index extended | Primary hand |

### 1.3 Dramatic Performance Actions
| Action Identifier | Facial Expression | Brow / Eye Dynamics | Viseme / Mouth Shape | Breath Pacing |
| :--- | :--- | :--- | :--- | :--- |
| **`speak`** | Articulated speech | Subtle emphasis twitch | Open phoneme cycle | Synchronous |
| **`listen`** | Attentive tilt | Wide curious pupil | Gentle neutral closure | Deep slow |
| **`laugh`** | Upward cheek swell | Squinting arc eye | Wide open + teeth & tongue | Rapid chest heave |
| **`cry`** | Downward lip tremble | Inward raised brows | Compressed down-curve | Ragged shudder |
| **`surprise`** | Backward head recoil | Dilated pupil, high arch | Vertical ellipse drop | Sharp inhale |
| **`fear`** | High protective hunched shoulders | Tense wide sclera | Shuddering grimace | Shallow rapid |
| **`anger`** | Forward aggressive thrust | Steep V-furrow | Bared clenched jaw | Heavy exhales |
| **`relief`** | Downward shoulder slump | Soft relaxed blink | Slow exhale smile | Long release |
| **`think`** | Upward lateral gaze shift | One brow cocked | Tight pursed lips | Subdued |
| **`react`** | Rapid orientation change | Responsive tracking | Contextual snap | Sudden catch |

### 1.4 Physical Events & Stunts
| Action Identifier | Involuntary Dynamics | Balance Recovery | Foot-Locking State | Hazard Type |
| :--- | :--- | :--- | :--- | :--- |
| **`slip`** | Sudden forward leg kick (`+60px`, `+95px`) | Severe backward tilt ($-0.65$) | Broken (slick surface) | Loss of traction |
| **`trip`** | Forward foot snag with forward fall | Pitch-forward ($+0.70$) | Stumbled | Obstacle collision |
| **`fall`** | Gravity-driven downward acceleration | Airborne tumble | Zero contact | Height drop |
| **`catch_balance`** | Asymmetric arm windmilling (`±sw * 0.85`) | Wide stance bracing | Re-engaging | Dynamic recovery |
| **`hang`** | Pure suspension from finger grip coordinates | Dangling legs | Airborne | Edge drop / Cliff |
| **`recover`** | Upright torso recentering & footing reset | Stabilized stance | Fully locked | Return to neutral |
| **`sit`** | $90^\circ$ hip/knee flexion to seat height | Contact with bench | Planted feet | Seated rest |
| **`stand`** | Upward quadriceps thrust to full height | Ground push-off | Ground-locked | Transition |

---

## 2. COMPOSABLE ACTION SEQUENCING EXAMPLE

Any complex story beat is expressed as a temporal chain of primitives in the `ProductionScenePackage` JSON without custom code.

**Example: The Bridge Incident Sequence**
```text
sprint (t: 0.0s - 4.5s)
  -> slip (t: 4.5s - 5.8s, loss_of_sandal: right)
  -> catch_balance (t: 5.8s - 7.0s, arm_windmill: true)
  -> hang (t: 7.0s - 9.5s, grip_target: bridge_railing, letter_held_high: true)
  -> recover (t: 9.5s - 11.0s, return_to_standing)
  -> relief (t: 11.0s - 13.0s, hand_on_chest, exhale)
```

The state machine blends joint angles continuously across transitions using ease-in-out spherical interpolation, ensuring zero frame tearing or robotic jumps.
