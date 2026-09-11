/**
 * POD 006 - Persona 3 Reload Water Caustics & Dark Hour Particle Engine
 * High-performance 60fps canvas effect
 */

(function () {
  const canvas = document.getElementById('caustics-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  let width = (canvas.width = window.innerWidth);
  let height = (canvas.height = window.innerHeight);

  window.addEventListener('resize', () => {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  });

  // Floating Cyan Motes / Persona 3 bubbles
  const PARTICLE_COUNT = 45;
  const particles = [];

  for (let i = 0; i < PARTICLE_COUNT; i++) {
    particles.push({
      x: Math.random() * width,
      y: Math.random() * height,
      size: Math.random() * 2.5 + 0.8,
      speedY: Math.random() * 0.45 + 0.15,
      speedX: (Math.random() - 0.5) * 0.2,
      opacity: Math.random() * 0.6 + 0.2,
      pulse: Math.random() * Math.PI * 2,
    });
  }

  let time = 0;

  function render() {
    time += 0.015;
    ctx.clearRect(0, 0, width, height);

    // Deep Midnight Navy Gradient
    const bgGradient = ctx.createLinearGradient(0, 0, width, height);
    bgGradient.addColorStop(0, '#010c1a');
    bgGradient.addColorStop(0.5, '#021833');
    bgGradient.addColorStop(1, '#000814');
    ctx.fillStyle = bgGradient;
    ctx.fillRect(0, 0, width, height);

    // Subtle Water Caustics Shimmer Layers
    ctx.save();
    ctx.globalCompositeOperation = 'screen';

    // Caustic Wave 1
    ctx.beginPath();
    ctx.strokeStyle = 'rgba(0, 212, 255, 0.045)';
    ctx.lineWidth = 38;
    for (let x = 0; x < width; x += 35) {
      const y =
        height * 0.35 +
        Math.sin(x * 0.005 + time * 0.7) * 45 +
        Math.cos(x * 0.009 - time * 0.5) * 30;
      if (x === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Caustic Wave 2
    ctx.beginPath();
    ctx.strokeStyle = 'rgba(31, 162, 255, 0.035)';
    ctx.lineWidth = 55;
    for (let x = 0; x < width; x += 40) {
      const y =
        height * 0.65 +
        Math.cos(x * 0.004 + time * 0.6) * 55 +
        Math.sin(x * 0.007 + time * 0.4) * 35;
      if (x === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Subtle Angled P3R Diagonal Accent Grid
    ctx.strokeStyle = 'rgba(0, 212, 255, 0.018)';
    ctx.lineWidth = 1;
    const spacing = 75;
    for (let x = -height; x < width + height; x += spacing) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x + height * 0.35, height);
      ctx.stroke();
    }

    ctx.restore();

    // Render Floating Glowing Cyan Particles
    ctx.save();
    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      p.y -= p.speedY;
      p.x += p.speedX + Math.sin(time + p.pulse) * 0.25;
      p.pulse += 0.02;

      // Wrap around
      if (p.y < -10) {
        p.y = height + 10;
        p.x = Math.random() * width;
      }
      if (p.x < -10) p.x = width + 10;
      if (p.x > width + 10) p.x = -10;

      const currentOpacity =
        p.opacity * (0.6 + 0.4 * Math.sin(p.pulse));

      // Glow halo
      const radial = ctx.createRadialGradient(
        p.x,
        p.y,
        0,
        p.x,
        p.y,
        p.size * 3.5
      );
      radial.addColorStop(0, `rgba(0, 240, 255, ${currentOpacity})`);
      radial.addColorStop(0.4, `rgba(0, 180, 255, ${currentOpacity * 0.5})`);
      radial.addColorStop(1, 'rgba(0, 212, 255, 0)');

      ctx.fillStyle = radial;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size * 3.5, 0, Math.PI * 2);
      ctx.fill();

      // Core mote
      ctx.fillStyle = `rgba(220, 250, 255, ${currentOpacity * 0.9})`;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size * 0.7, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();

    requestAnimationFrame(render);
  }

  requestAnimationFrame(render);
})();
