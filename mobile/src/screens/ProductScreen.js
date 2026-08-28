import React from 'react';

export default function ProductScreen({ route, navigation }) {
  const { productId } = route.params || {};
  return {
    title: 'Товар #' + (productId || '?'),
    body: 'Фото, описание, цена, наличие, кнопка «В корзину», «🚀 Продвинуть», метки маркировки (labels), рейтинг продавца.',
    actions: [
      { label: 'В корзину', onPress: () => navigation.navigate('Cart') },
    ],
  };
}
