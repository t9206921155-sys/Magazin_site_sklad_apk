// Гео-поиск: товары/продавцы рядом
import React from 'react';

export default function SearchGeoScreen({ navigation }) {
  return {
    title: 'Поиск рядом',
    body: 'Поиск товаров по городу и радиусу. В дальнейшем — интеграция с картой и геолокацией.',
    actions: [
      { label: 'В каталог', onPress: () => navigation.navigate('Catalog') },
    ],
  };
}
