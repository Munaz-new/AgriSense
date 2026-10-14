import React from 'react';
import { Pressable,Text,TextInput,View } from 'react-native';
import { s,colors } from '../theme';
import { Icon,IconName } from './Icon';
export const date=(value: string) => new Date(value).toLocaleString();
export function Button({ title,onPress,disabled=false,secondary=false,icon,selected,accessibilityLabel }: { title: string; onPress: () => void; disabled?: boolean; secondary?: boolean; icon?: IconName; selected?: boolean; accessibilityLabel?: string; }) {
  return <Pressable accessibilityRole="button" accessibilityLabel={accessibilityLabel} accessibilityState={{ disabled,...(selected===undefined?{}:{selected}) }} disabled={disabled} onPress={onPress} style={({ pressed }) => [s.button,secondary&&s.secondary,disabled&&s.disabled,selected&&{ borderWidth: 1,borderColor: colors.green },pressed&&{ opacity: .75 }]}>
    {icon&&<Icon name={icon} size={20} color={secondary? colors.green:'#FFF'} />}<Text style={[s.buttonText,secondary&&s.secondaryText,{ flexShrink: 1 }]}>{title}</Text>
  </Pressable>;
}
export function Field({ label,value,setValue,numeric=false,disabled=false,multiline=false,maxLength=100 }: { label: string; value: string; setValue: (text: string) => void; numeric?: boolean; disabled?: boolean; multiline?: boolean; maxLength?: number; }) {
  return <View style={s.field}>
    <Text style={s.label}>{label}</Text>
    <TextInput accessibilityLabel={label} style={[s.input,multiline&&{ minHeight: 80,textAlignVertical: 'top' }]} editable={!disabled} value={value} onChangeText={setValue} keyboardType={numeric? 'numbers-and-punctuation':'default'} maxLength={maxLength} multiline={multiline} />
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
