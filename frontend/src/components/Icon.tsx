import React from 'react';
import { View } from 'react-native';
import { colors } from '../theme';
export type IconName='home'|'plants'|'scan'|'history'|'more'|'plus'|'arrow';
// Original geometric marks, drawn with React Native primitives. No font or asset dependency.
export function Icon({ name,color=colors.green,size=24 }: { name: IconName; color?: string; size?: number; }) {
  const line={ position: 'absolute' as const,backgroundColor: color,borderRadius: 2 };
  return <View accessible={false} accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={{ width: size,height: size }}>
    {name==='plants'&&<>
      <View style={{ position: 'absolute',width: size*.48,height: size*.65,left: size*.4,top: 1,borderWidth: 2,borderColor: color,borderTopLeftRadius: size,borderBottomRightRadius: size,transform: [{ rotate: '15deg' }] }} />
      <View style={[line,{ width: 2,height: size*.7,left: size*.45,top: size*.3,transform: [{ rotate: '28deg' }] }]} />
      <View style={{ position: 'absolute',width: size*.4,height: size*.3,left: 0,top: size*.4,borderWidth: 2,borderColor: color,borderTopRightRadius: size,borderBottomLeftRadius: size }} />
    </>}
    {name==='home'&&<>
      <View style={{ position: 'absolute',width: size*.55,height: size*.55,borderLeftWidth: 2,borderTopWidth: 2,borderColor: color,left: size*.22,top: size*.12,transform: [{ rotate: '45deg' }] }} />
      <View style={{ position: 'absolute',width: size*.65,height: size*.52,borderWidth: 2,borderTopWidth: 0,borderColor: color,left: size*.18,bottom: 1,borderRadius: 2 }} />
    </>}
    {name==='scan'&&<>
      <View style={{ position: 'absolute',left: 1,right: 1,top: 4,bottom: 2,borderWidth: 2,borderColor: color,borderRadius: 5 }} />
      <View style={{ position: 'absolute',left: size*.34,top: size*.38,width: size*.33,height: size*.33,borderWidth: 2,borderColor: color,borderRadius: size }} />
      <View style={[line,{ width: size*.35,height: 3,left: size*.33,top: 1 }]} />
    </>}
    {name==='history'&&<>
      <View style={{ position: 'absolute',inset: 1,borderWidth: 2,borderColor: color,borderRadius: size }} />
      <View style={[line,{ width: 2,height: size*.35,top: size*.2,left: size*.48 }]} />
      <View style={[line,{ height: 2,width: size*.25,top: size*.5,left: size*.48 }]} />
    </>}
    {name==='more'&&[0,1,2].map(i => <View key={i} style={[line,{ width: 4,height: 4,top: size/2-2,left: i*(size-4)/2 }]} />)}
    {name==='plus'&&<>
      <View style={[line,{ width: 2,height: size*.7,left: size/2-1,top: size*.15 }]} />
      <View style={[line,{ height: 2,width: size*.7,top: size/2-1,left: size*.15 }]} />
    </>}
    {name==='arrow'&&<View style={{ position: 'absolute',width: size*.4,height: size*.4,borderTopWidth: 2,borderRightWidth: 2,borderColor: color,transform: [{ rotate: '45deg' }],top: size*.3,left: size*.2 }} />}
  </View>;
}
