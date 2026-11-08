import {makeProject} from '@motion-canvas/core';
import odeonsplatz_scene from './scenes/odeonsplatz_scene?scene';
import odeonsplatz_sequence_v41 from './scenes/odeonsplatz_sequence_v41?scene';

export default makeProject({
  scenes: [
    odeonsplatz_sequence_v41,
    odeonsplatz_scene,
  ],
});
