import React,{ useState } from 'react';
import { Pressable,Text,View } from 'react-native';
import { Journal } from '../hooks/useJournal';
import { s } from '../theme';
import { Title,Button } from '../components/UI';
import { Icon } from '../components/Icon';
const sections=[
  ['About AgriSense','A growing record of your plants','AgriSense is a plant observation journal. Give each physical plant its own profile, save photos and field context, and revisit its history.'],
  ['How AgriSense works','From first photo to plant history','1. Add or select your plant.\n2. Capture or choose a photo.\n3. Validate the image and enter field context.\n4. Save without analysis, or analyze a tomato leaf when the model is available.\n5. Revisit the same plant over time.'],
  ['Project information','The current stage of the project','AgriSense supports plant records and tomato-leaf analysis when the model and plant suitability screening are available. Screening and disease predictions can be wrong. Severity and health progression remain unavailable.'],
  ['Help','Photos, records and retries','Use a well-lit JPEG, PNG or WebP photo. File validation does not verify plant content. If a save times out, check history and retry the same save. Exact-image reuse is flagged and is not new progression evidence. Camera access needs permission; you can also select a photo.'],
  ['Settings','Connection and storage','Records are stored by your connected AgriSense service. Browser photo drafts can be kept locally and are retained before a save for recovery. Native drafts last only for this app session. There are no cloud accounts or notifications to configure.'],
];
export function MoreScreen({ j }: { j: Journal; }) {
  const [open,setOpen]=useState<string|null>(null);
  return <>
    <Title title="A little more" subtitle="Get to know your plant journal." />
    <View style={s.hero}>
      <Icon name="plants" size={40} color="#D4E6C9" />
      <Text style={s.heroTitle}>Rooted in observation.</Text>
      <Text style={s.heroBody}>An honest record today. A foundation for understanding tomorrow.</Text>
    </View>{sections.map(([title,sub,body]) => <View style={s.card} key={title}>
      <Pressable accessibilityRole="button" accessibilityState={{ expanded: open===title }} onPress={() => setOpen(open===title? null:title)} style={[s.row,{ minHeight: 48 }]}>
        <View style={s.flex}>
          <Text style={s.heading}>{title}</Text>
          <Text style={s.muted}>{sub}</Text>
        </View>
        <Icon name="arrow" />
      </Pressable>{open===title&&<Text style={s.body}>{body}</Text>}{open==='Settings'&&title==='Settings'&&<>
        <Text style={s.notice}>{j.health? `Observation service connected · ${j.health.capabilities.tomato_analysis? 'Tomato analysis available':'Record-only mode'}`:'Observation service not connected'}</Text>
        <Button title="Check connection" secondary disabled={j.busy} onPress={() => void j.refresh()} />
      </>}</View>)}<Text style={[s.muted,{ textAlign: 'center' }]}>AgriSense · Your plants, one observation at a time.</Text>
  </>;
}
