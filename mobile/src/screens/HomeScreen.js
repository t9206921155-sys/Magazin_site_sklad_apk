// Главный экран мобильного приложения
import React from 'react';

export default function HomeScreen({ navigation }) {
  return {
    title: 'Telegram Shop',
    body: 'Главная страница мобильного приложения покупателя. В дальнейшем — лента рекомендаций, категории, баннеры.',
    actions: [
      { label: 'В каталог', onPress: () => navigation.navigate('Catalog') },
      { label: 'Мои заказы', onPress: () => navigation.navigate('Orders') },
    ],
  };
}
