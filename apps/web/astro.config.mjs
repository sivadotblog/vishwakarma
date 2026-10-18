// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
	site: 'https://sivadotblog.github.io',
	base: '/vishwakarma',
	integrations: [
		starlight({
			title: 'Vishwakarma',
			social: [
				{
					icon: 'github',
					label: 'GitHub',
					href: 'https://github.com/sivadotblog/vishwakarma',
				},
			],
			sidebar: [
				{
					label: 'Getting Started',
					items: [{ autogenerate: { directory: 'getting-started' } }],
				},
				{
					label: 'Concepts',
					items: [{ autogenerate: { directory: 'concepts' } }],
				},
				{
					label: 'How-to Guides',
					items: [{ autogenerate: { directory: 'how-to-guides' } }],
				},
				{
					label: 'Advanced',
					items: [{ autogenerate: { directory: 'advanced' } }],
				},
				{
					label: 'Examples',
					items: [{ autogenerate: { directory: 'examples' } }],
				},
				{
					label: 'Integrations',
					items: [{ autogenerate: { directory: 'integrations' } }],
				},
				{
					label: 'API Reference',
					items: [{ autogenerate: { directory: 'api-reference' } }],
				},
				{
					label: 'Contribute',
					items: [{ autogenerate: { directory: 'contribute' } }],
				},
				{
					label: 'Release Notes',
					items: [{ autogenerate: { directory: 'release-notes' } }],
				},
			],
		}),
	],
});
