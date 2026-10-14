// Render actual UI components with DOM equivalents for React Native primitives.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import * as recordState from '../src/recordState.ts';
import * as guidance from '../src/treatmentGuidance.ts';
const root = fileURLToPath(new URL('../src/', import.meta.url));
const primitive = ({ children }) => React.createElement('div', null, children);
function load(path) {
  const source = readFileSync(path, 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true } }).outputText;
  const exports = {};
  runInNewContext(compiled, { exports, require(name) {
    if (name === 'react') return React;
    if (name === 'react-native') return { Platform: { OS: 'web' }, Text: primitive, View: primitive, ScrollView: primitive, Pressable: primitive, Image: ({ source }) => React.createElement('img', { src: source.uri }), Linking: {} };
    if (name.endsWith('/theme')) return { s: {} };
    if (name.endsWith('/api')) return { API_URL: 'http://test-only' };
    if (name.endsWith('/recordState')) return recordState;
    if (name.endsWith('/treatmentGuidance')) return guidance;
    if (name.endsWith('/Icon')) return { Icon: () => null };
    if (name.endsWith('/UI')) return { Badge: primitive, Empty: primitive, Title: primitive,
      Field: ({label}) => React.createElement('label', null, label), date: value => value,
      Button: ({ title, disabled }) => React.createElement('button', { disabled }, title) };
    return load(resolve(dirname(path), name + '.tsx'));
  } });
  return exports;
}
const { ObservationCard } = load(resolve(root, 'components/ObservationCard.tsx'));
const { PlantsScreen } = load(resolve(root, 'screens/PlantsScreen.tsx'));
const real = { id: 'render-test', plant_id: 'p', image_path: '/test.png', created_at: '2026-01-01', observed_at: '2026-01-01', observed_timezone: 'Asia/Kolkata (UTC+05:30)', disease: 'Early_blight', confidence: 72.5, severity: null, is_mock: false, analysis_status: 'completed', temperature: null, humidity: null, soil_type: null, soil_condition: null };

test('saved result/history card renders prediction, uncertainty, sourced guidance and missing environment', () => {
  const html = renderToStaticMarkup(React.createElement(ObservationCard, { observation: real }));
  for (const text of ['Early_blight', 'Experimental AI prediction — not a validated diagnosis', 'uncalibrated', 'do not represent verified correctness', 'Treatment and management guidance', 'UMN Extension', 'Temperature not recorded', 'Humidity not recorded', 'Asia/Kolkata']) assert.ok(html.includes(text), text);
});

test('record-only and historical mock cards do not render treatment guidance', () => {
  for (const patch of [{ is_mock: true }, { analysis_status: 'not_requested', disease: null }]) {
    const html = renderToStaticMarkup(React.createElement(ObservationCard, { observation: { ...real, ...patch } }));
    assert.ok(!html.includes('Treatment and management guidance'));
  }
});

test('Scan renders backend address, actual error and a photo-check retry without a prediction', () => {
  const { ScanScreen } = load(resolve(root, 'screens/ScanScreen.tsx'));
  const j = { plants:[{id:'p',crop_name:'tomato'}], selected:{id:'p',crop_name:'tomato'},
    image:{uri:'file:///camera.jpg'}, suitability:{status:'unavailable',message:'Screening unavailable'},
    validation:null, error:'Photo upload failed; backend receipt is unknown.' };
  const html = renderToStaticMarkup(React.createElement(ScanScreen, {j}));
  for (const text of ['Backend: http://test-only','Photo upload failed; backend receipt is unknown.','Retry photo checks']) assert.ok(html.includes(text));
  assert.ok(!html.includes('Disease analysis completed'));
});

test('Home reports current backend availability rather than hardcoded future availability', () => {
  const { HomeScreen } = load(resolve(root, 'screens/HomeScreen.tsx'));
  const j = { records: {}, plants: [], selected: null, health: { analysis_message: 'Tomato classification available.', capabilities: { record_only: true } } };
  const html = renderToStaticMarkup(React.createElement(HomeScreen, { j }));
  assert.ok(html.includes('Tomato classification available.'));
  assert.ok(!html.includes('will become available'));
});

test('Scan renders the current preview and distinct file, suitability and disease stages', () => {
  const { ScanScreen } = load(resolve(root, 'screens/ScanScreen.tsx'));
  const base = { plants: [{ id: 'p', crop_name: 'tomato' }], selected: { id: 'p', crop_name: 'tomato' },
    health: { capabilities: { tomato_analysis: true } }, image: { uri: 'current-logo.png', fileName: 'current-logo.png' }, imageRevision: 2,
    validation: { is_valid: true, message: 'File checks only' }, analysisBlockers: [], recordBlockers: [], observedAt: '2026-01-01' };
  for (const [status, label] of [['not_checked','Plant suitability not checked'], ['accepted','Plant-like content detected; tomato identity is not verified.'],
    ['rejected','Image rejected — non-plant content'], ['inconclusive','Image rejected for analysis — plant content uncertain'],
    ['unavailable','Plant suitability unavailable']]) {
    const html = renderToStaticMarkup(React.createElement(ScanScreen, { j: { ...base, suitability: { status, message: 'Screening detail' } } }));
    assert.ok(html.includes('src="current-logo.png"'));
    for(const label of ['Retake Photo','Choose from Gallery','Cancel photo','Use photo','HTTPS or localhost']) assert.ok(html.includes(label),label);
    assert.ok(html.includes('File validation passed'));
    assert.ok(html.includes(label), label);
    assert.ok(html.includes('Disease analysis has not completed'));
    assert.ok(!html.includes('Disease analysis completed'));
  }
  const completed = renderToStaticMarkup(React.createElement(ObservationCard, { observation: real }));
  assert.ok(completed.includes('Disease analysis completed'));
  const record = renderToStaticMarkup(React.createElement(ObservationCard, { observation: { ...real, analysis_status: 'not_requested' } }));
  assert.ok(!record.includes('Disease analysis completed'));
});

test('Scan exposes Take Photo separately from gallery and disables replacement for uncertain saves',()=>{
  const {ScanScreen}=load(resolve(root,'screens/ScanScreen.tsx'));
  const j={plants:[{id:'p',crop_name:'tomato'}],selected:{id:'p',crop_name:'tomato'},health:null,
    image:null,suitability:{status:'not_checked'},analysisBlockers:[],recordBlockers:[]};
  const initial=renderToStaticMarkup(React.createElement(ScanScreen,{j}));
  assert.ok(initial.includes('Take Photo'));assert.ok(initial.includes('Choose from Gallery'));
  const locked=renderToStaticMarkup(React.createElement(ScanScreen,{j:{...j,image:{uri:'pending.jpg'},locked:true,pendingId:'pending'}}));
  for(const label of ['Retake Photo','Choose from Gallery','Cancel photo']) assert.ok(locked.includes(`<button disabled="">${label}</button>`),label);
});

test('plant UI keeps plant names and crop metadata distinct and offers explicit crop selection/editing',()=>{
  const j={plants:[{id:'unknown',name:'Unknown',crop_name:'Leaf',created_at:'2026-01-01'},
    {id:'named-tomato',name:'tomato',crop_name:null,created_at:'2026-01-01'}],selected:null,records:{},
    cropChoice:'tomato',cropName:'',name:'',setName(){},setCropName(){},chooseCrop(){},locked:false,busy:false,
    pendingId:null,pendingPlant:null,setCropChoice(){},selectPlant(){},startScan(){},openHistory(){},refresh(){},addPlant(){},discardPendingPlant(){}};
  const html=renderToStaticMarkup(React.createElement(PlantsScreen,{j}));
  for(const text of ['Plant name / identifier','Crop (choose what this plant is)','Tomato','Other crop','Not recorded',
    'Unknown','Crop: Leaf','tomato','Crop: Not recorded','Edit crop for Unknown','Edit crop for tomato']) assert.ok(html.includes(text),text);
  assert.ok(!html.includes('Unknown · Leaf'));
  assert.ok(!html.includes('tomato · Crop not recorded'));
});

test('Scan explains missing tomato selection and routes to creating/editing without clearing the photo',()=>{
  const {ScanScreen}=load(resolve(root,'screens/ScanScreen.tsx'));
  const j={plants:[{id:'p',name:'Leaf 1',crop_name:'Leaf'}],selected:{id:'p',name:'Leaf 1',crop_name:'Leaf'},
    health:{capabilities:{tomato_analysis:true}},image:{uri:'kept-photo.jpg'},validation:{is_valid:true},suitability:{status:'accepted'},
    analysisBlockers:['Select or create a plant with crop set to tomato.'],recordBlockers:[],analysisBlockers:[],observedAt:'2026-01-01',
    navigate(){},chooseCrop(){},locked:false};
  const html=renderToStaticMarkup(React.createElement(ScanScreen,{j:{...j,analysisBlockers:['Select or create a plant with crop set to tomato.']}}));
  assert.ok(html.includes('Select a plant with crop set to tomato'));
  assert.ok(html.includes('Create a tomato plant'));
  assert.ok(html.includes('Edit selected plant crop'));
  assert.ok(html.includes('src="kept-photo.jpg"'));
});
