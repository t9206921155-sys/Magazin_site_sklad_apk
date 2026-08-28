import React from 'react';

export default function CatalogScreen({ navigation }) {
  return {
    title: 'Каталог',
    body: 'Фильтры по категории, цене, городу (гео-поиск), сортировка. Интеграция с /api/catalog и /api/search/geo.',
    actions: [
      { label: 'Поиск рядом', onPress: () => navigation.navigate('SearchGeo') },
      { label: 'В корзину', onPress: () => navigation.navigate('Cart') },
    ],
  };
}
