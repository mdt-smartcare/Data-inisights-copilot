import sharp from 'sharp';
import fs from 'fs';
import path from 'path';

const sizes = [192, 512];
const svgPath = './public/logo.svg';
const outputDir = './public';

async function generateIcons() {
  const svgBuffer = fs.readFileSync(svgPath);
  
  for (const size of sizes) {
    // Create a square canvas with white background and centered logo
    const background = Buffer.from(
      `<svg width="${size}" height="${size}" xmlns="http://www.w3.org/2000/svg">
        <rect width="100%" height="100%" fill="white"/>
      </svg>`
    );
    
    // Resize the logo to fit within the square (with padding)
    const logoSize = Math.floor(size * 0.8);
    const resizedLogo = await sharp(svgBuffer)
      .resize(logoSize, Math.floor(logoSize * 47 / 327), { fit: 'contain' })
      .toBuffer();
    
    // Composite the logo onto the white background
    const logoHeight = Math.floor(logoSize * 47 / 327);
    const top = Math.floor((size - logoHeight) / 2);
    const left = Math.floor((size - logoSize) / 2);
    
    await sharp(background)
      .composite([{ input: resizedLogo, top, left }])
      .png()
      .toFile(path.join(outputDir, `icon-${size}.png`));
    
    console.log(`Generated icon-${size}.png`);
  }
}

generateIcons().catch(console.error);
