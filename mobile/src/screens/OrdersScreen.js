import React from 'react';

export default function OrdersScreen({ navigation }) {
  return {
    title: 'Мои заказы',
    body: 'История заказов, статусы (оформлен, оплачен, в пути, доставлен), трекинг, кнопка «Оставить отзыв».',
    actions: [
      { label: 'В каталог', onPress: () => navigation.navigate('Catalog') },
    ],
  };
}
