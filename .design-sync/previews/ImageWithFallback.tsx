import * as React from 'react';
import { ImageWithFallback } from 'verifarms-frontend';

const SVG =
  "<svg xmlns='http://www.w3.org/2000/svg' width='240' height='140'>" +
  "<rect width='240' height='140' rx='12' fill='#0B1F16'/>" +
  "<circle cx='120' cy='60' r='26' fill='#4ADE80'/>" +
  "<text x='120' y='118' fill='#E8F0EA' font-family='sans-serif' font-size='15' text-anchor='middle'>VeriFarm field</text>" +
  "</svg>";
const OK_SRC = `data:image/svg+xml;utf8,${encodeURIComponent(SVG)}`;

export const Loaded = () => (
  <ImageWithFallback
    src={OK_SRC}
    alt="A verified farm field"
    style={{ width: 240, height: 140, borderRadius: 12, objectFit: 'cover' }}
  />
);

export const BrokenFallsBack = () => (
  <ImageWithFallback
    src="https://invalid.example/missing.png"
    alt="Missing image"
    style={{ width: 240, height: 140 }}
  />
);
