import React from 'react';
import { Linking,Text,View } from 'react-native';
import type { Observation } from '../api';
import { treatmentGuidance,GUIDANCE_LIMITATIONS } from '../treatmentGuidance';
import { s } from '../theme';

export function TreatmentGuidance({ observation }: { observation: Observation }) {
  const guidance=treatmentGuidance(observation);
  const [linkError,setLinkError]=React.useState('');
  if(!guidance) return null;
  return <View style={s.section}>
    <Text style={s.heading}>Treatment and management guidance</Text>
    <Text style={s.notice}>{GUIDANCE_LIMITATIONS}</Text>
    {guidance.steps.map(step => <Text key={step} style={s.body}>{step}</Text>)}
    {guidance.sources.map(source => <Text key={source.url} accessibilityRole="link" style={[s.body,{ textDecorationLine: 'underline' }]} onPress={() => {
      setLinkError('');
      void Linking.openURL(source.url).catch(() => setLinkError(`Could not open source: ${source.url}`));
    }}>{source.title}</Text>)}
    {!!linkError&&<Text style={s.error}>{linkError}</Text>}
    <Text style={s.muted}>Guidance reviewed 8 October 2026. It does not change the saved model prediction.</Text>
  </View>;
}
