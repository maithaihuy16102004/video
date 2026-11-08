import path from 'node:path';
import { renderProductionVideo } from './production_render_service.mjs';

const OUT_DIR = path.resolve('output/Universal_Cinematic_Pipeline_V421_Renderer_Recovery');

async function renderAll() {
  console.log('================================================================');
  console.log('BATCH RENDERING ALL 6 V4.2.3 PROOF & GENERALIZATION VIDEOS');
  console.log('================================================================\n');

  const jobs = [
    {
      sceneType: 'edo_bridge',
      durationSec: 12.0,
      audioPath: path.resolve('output/v421_audio/proof_a_mixed.wav'),
      outputPath: path.join(OUT_DIR, 'v423_recovered_edo_bridge_proof.mp4')
    },
    {
      sceneType: 'edo_house',
      durationSec: 8.5,
      audioPath: path.resolve('output/v421_audio/proof_b_mixed.wav'),
      outputPath: path.join(OUT_DIR, 'v423_recovered_edo_house_proof.mp4')
    },
    {
      sceneType: 'modern_lab',
      durationSec: 7.0,
      audioPath: path.resolve('output/v421_audio/proof_c_mixed.wav'),
      outputPath: path.join(OUT_DIR, 'v423_recovered_modern_lab_proof.mp4')
    },
    {
      packagePath: path.resolve('output/unseen_packages/package_01_victorian_london.json'),
      audioPath: path.resolve('output/unseen_audio/victorian_london_mixed.wav'),
      outputPath: path.join(OUT_DIR, 'v423_unseen_01_victorian_london.mp4')
    },
    {
      packagePath: path.resolve('output/unseen_packages/package_02_hanoi_coffee.json'),
      audioPath: path.resolve('output/unseen_audio/hanoi_coffee_mixed.wav'),
      outputPath: path.join(OUT_DIR, 'v423_unseen_02_hanoi_coffee.mp4')
    },
    {
      packagePath: path.resolve('output/unseen_packages/package_03_antarctic_aurora.json'),
      audioPath: path.resolve('output/unseen_audio/antarctic_aurora_mixed.wav'),
      outputPath: path.join(OUT_DIR, 'v423_unseen_03_antarctic_aurora.mp4')
    }
  ];

  for (let i = 0; i < jobs.length; i++) {
    const job = jobs[i];
    console.log(`\n>>> STARTING JOB ${i + 1}/${jobs.length}: ${path.basename(job.outputPath)}`);
    await renderProductionVideo(job);
    console.log(`<<< FINISHED JOB ${i + 1}/${jobs.length}\n`);
  }

  console.log('ALL 6 VIDEOS RENDERED SUCCESSFULLY!');
}

renderAll().catch(err => {
  console.error('Fatal batch render failure:', err);
  process.exit(1);
});
