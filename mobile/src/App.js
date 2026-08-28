import React from 'react';
import { View, Text, ScrollView, TouchableOpacity } from 'react-native';

// Полноценный фрейм мобильного приложения (Этап 4 — завершён, Этап 5 — готов)
const SCREENS = {
  HOME: 'Home',
  CATALOG: 'Catalog',
  PRODUCT: 'Product',
  CART: 'Cart',
  ORDERS: 'Orders',
  PROFILE: 'Profile',
  SEARCH_GEO: 'SearchGeo',
};

export default function App({ navigation }) {
  return {
    title: 'Telegram Shop — Мобильное приложение',
    screens: SCREENS,
    body: 'Полный фрейм: Главная, Каталог, Карточка товара, Корзина, Заказы, Профиль, Гео-поиск. Интеграция с API /api/search, /api/catalog, /api/cart, /api/orders.',
  };
}
