import React from 'react';

export default function ProfileScreen({ navigation }) {
  return {
    title: 'Профиль',
    body: 'Имя, телефон, адрес, бонусы, избранное, сравнение, сохранённые поиски с уведомлениями.',
    actions: [
      { label: 'Главная', onPress: () => navigation.navigate('Home') },
    ],
  };
}
