import React from 'react';
import { Image,Text,View } from 'react-native';
import { API_URL,Observation,Plant } from '../api';
import { recordLabels } from '../recordState';
import { s } from '../theme';
import { Badge,date } from './UI';
export function ObservationCard({ observation: o,plant,compact=false }: { observation: Observation; plant?: Plant|null; compact?: boolean; }) {
  const labels=recordLabels(o);
  return <View style={s.card}>
    <View style={s.row}>{compact&&<Image accessibilityLabel="Recorded plant photo" source={{ uri: `${API_URL}${o.image_path}` }} style={s.thumbnail} />}<View style={[s.flex,{ gap: 4 }]}>
      <Text style={s.heading}>{plant?.name||'Plant observation'}</Text>
      <Text style={s.muted}>{plant?.crop_name||'Crop not recorded'}</Text>
      <Text style={s.muted}>{date(o.observed_at||o.created_at)}{!o.observed_at? ' · saved':''}</Text>
    </View>
    </View>
    {!compact&&<Image accessibilityLabel="Recorded plant photo" source={{ uri: `${API_URL}${o.image_path}` }} style={s.photo} />}
    <Badge>{o.is_mock? 'Historical synthetic record':o.analysis_status==='not_requested'? 'Not assessed':'Stored analysis'}</Badge>
    {!compact&&<>
      <View style={s.section}>
        <Text style={s.heading}>{labels.disease}</Text>
        <Text style={s.body}>{labels.severity}</Text>
        <Text style={s.body}>{labels.confidence}</Text>
      </View>
      <Text style={s.notice}>{o.analysis_status==='not_requested'&&!o.is_mock? 'Recorded without validated disease analysis.':labels.notice}</Text>
      <View style={s.divider} />
      <Text style={s.eyebrow}>Observation details</Text>
      <Text style={s.muted}>{o.observed_at? `Observed ${date(o.observed_at)}`:'Observation time not supplied'}{'\n'}Saved {date(o.created_at)}</Text>
      <Text style={s.body}>{o.temperature}°C · {o.humidity}% humidity{'\n'}{o.soil_type} soil · {o.soil_condition}</Text>
      {o.tracking_ref&&<Text style={s.body}>Leaf / site: {o.tracking_ref}</Text>}{o.notes&&<Text style={s.body}>{o.notes}</Text>}
      <Text style={s.muted}>Environment is user-entered context only.</Text>
      {o.predictor&&<Text style={s.muted}>Analysis source: {o.predictor}</Text>}{o.checkpoint_id&&<Text style={s.muted}>Model artifact: {o.checkpoint_id}</Text>}
    </>}
    {o.duplicate_of&&<Text style={s.notice}>This exact image was recorded previously for this plant. It is not new progression evidence.</Text>}
  </View>;
}
