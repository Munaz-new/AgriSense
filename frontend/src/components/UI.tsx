import React from 'react';
import { Pressable,Text,TextInput,View } from 'react-native';
import { s,colors } from '../theme';
import { Icon,IconName } from './Icon';
export const date=(value: string) => new Date(value).toLocaleString();
export function Button({ title,onPress,disabled=false,secondary=false,icon }: { title: string; onPress: () => void; disabled?: boolean; secondary?: boolean; icon?: IconName; }) {
  return <Pressable accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} style={({ pressed }) => [s.button,secondary&&s.secondary,disabled&&s.disabled,pressed&&{ opacity: .75 }]}>
    {icon&&<Icon name={icon} size={20} color={secondary? colors.green:'#FFF'} />}<Text style={[s.buttonText,secondary&&s.secondaryText,{ flexShrink: 1 }]}>{title}</Text>
  </Pressable>;
}
export function Field({ label,value,setValue,numeric=false,disabled=false,multiline=false }: { label: string; value: string; setValue: (text: string) => void; numeric?: boolean; disabled?: boolean; multiline?: boolean; }) {
  return <View style={s.field}>
    <Text style={s.label}>{label}</Text>
    <TextInput accessibilityLabel={label} style={[s.input,multiline&&{ minHeight: 80,textAlignVertical: 'top' }]} editable={!disabled} value={value} onChangeText={setValue} keyboardType={numeric? 'numbers-and-punctuation':'default'} maxLength={100} multiline={multiline} />
  </View>;
}
export function Badge({ children }: { children: string; }) {
  return <View style={s.badge}>
    <Text style={s.badgeText}>{children}</Text>
  </View>;
}
export function Title({ title,subtitle }: { title: string; subtitle: string; }) {
  return <View style={{ gap: 6 }}>
    <Text accessibilityRole="header" style={s.title}>{title}</Text>
    <Text style={s.muted}>{subtitle}</Text>
  </View>;
}
export function Empty({ title,children }: { title: string; children: string; }) {
  return <View style={[s.card,s.empty]}>
    <Icon name="plants" size={38} />
    <Text style={s.heading}>{title}</Text>
    <Text style={[s.muted,{ textAlign: 'center' }]}>{children}</Text>
  </View>;
}
