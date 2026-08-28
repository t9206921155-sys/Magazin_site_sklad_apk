import React from 'react';

export default function CartScreen({ navigation }) {
  return {
    title: 'Корзина',
    body: 'Список товаров, изменение количества, удаление, оформление заказа (имя, телефон, адрес, комментарий), выбор доставки.',
    actions: [
      { label: 'Оформить заказ', onPress: () => navigation.navigate('Orders') },
    ],
  };
}
