--
-- PostgreSQL database dump
--

-- Dumped from database version 17.2
-- Dumped by pg_dump version 17.2

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: report; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.report (id, description, location, disaster_type, extracted_locations) FROM stdin;
1	There is a massive flood in mumbai	Mumbai	Flood	mumbai
2	It is flooding heavily in Delhi 	Delhi	Flood	Delhi
3	it is flooding in mumbai	mumbai	Flood	mumbai
4	it is flooding in Delhi	Delhi	Flood	Delhi
5	It is flooding heavily in Bandra	bandra	Flood	
6	It is flooding in Bandra	Bandra	Flood	
7	It is Flooding in Bandra 	Bandra	\N	
8	It is flooding in Pune 	Pune	\N	Pune
9	It is flooding in Kothrud	Kothrud	\N	Kothrud
10	It is flooding in Delhi	Delho	\N	Delhi
11	It is flooding in Borivalli	Borivalli	\N	Borivalli
12	It is flooding in Juhu	Juhu	\N	
13	It is flooding in Bandra	Bandra	\N	
14	It is flooding in Bandra	Bandra	\N	
15	It is flooding in Bandra	ba	\N	
16	It is flooding in Bandra	Bandra	\N	
17	It is flooding in kothrud	Kot	\N	
18	It is flooding in Kothrud	Kothrud	\N	
19	It is flooding in Kothrud	Kothrud	\N	
20	It is flooding in Kothrud	Kothrud	\N	
21	it is flooding really terribly in Kothrud	Kothrud	\N	
22	it is flooding quite terribly in kothrud	kothrud	Flood	
23	there is heavy rain on sinhagad road 	Sinhagad road	Flood	
24	there is lot of waterlogging in koregaon right now	Koregaon	Flood	koregaon
25	It is flodding heavily in bandra	Bandra	Unknown	
26	It is running heavily in Bibewadi	Bibewadi	Unknown	Bibewadi
27	it flooding heavily in  Swargate	Swargate	Flood	
28	there is waterlogging in Pimpri-Chinchwad	Pimpri-Chinchwad	Flood	
29	There is waterlogging in Bibewadi	Bibewadi	Flood	Bibewadi
30	It is raining heavily in bibewadi	bibewadi	Unknown	
31	there is waterlogging in Bibewadi	Bibewadi	Flood	Bibewadi
32	there is waterlogging in Viman Nagar	Viman nagar	Flood	Viman Nagar
\.


--
-- Data for Name: user; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public."user" (id, username, email, password_hash) FROM stdin;
2	lhase123	parthlhase@gmail.com	scrypt:32768:8:1$q6QrwQHAgNsBE4rO$8a296278a664a4e6d067c497724e72e894e76eb3f565667b387f3ff6ece923da80fbbe9e8520504cbf3b077e653c22017d8180ede5d1b1bca543e2cdac43f72c
3	saddam_hussein	bombwebsite@gmail.com	scrypt:32768:8:1$5LJwztdvKR3sg6Mp$fcd484557e03315cfa7a2acb7df2bf0938c19d2639008d6515faeb9009f4741d3b6448db5eb146f883b709ea6dd7677536dd4a8851b3d9994dfd8aa831fffe3a
4	winston_bhau_churchil	winstonchurchill@gmail.com	scrypt:32768:8:1$2Qk2sXEEYruuQuOQ$4387e685d06d4156aae51163c98c3fabf70cf4c9aede58c4d34b2e5487edf321b4c7a9975624bc6565a11a196d91826a23c159559b2b6f518521610b4003c2fc
5	tushar	tualibag@gmail.com	scrypt:32768:8:1$mibcQB6DXxN3VRWL$e5b0366223dd7c619f27abc1e7e55776b002e9f7186e837544b94df4a915dcbbd7cdc03f9ed762a01315adfd651bec8199f617447b08291483dc427c79b77e58
6	soham_walimbe	sohamwalimbe20@gmail.com	scrypt:32768:8:1$HiFtDipGrgFyFdDG$cbb88e25e58631241ad940b2feadc988151762a5e6243a4575bc14b814bd251b9655c25b525674e3c04339aabc7dfe3f322dee0fe3142efa722bf60d633d5dde
\.


--
-- Name: report_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.report_id_seq', 32, true);


--
-- Name: user_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.user_id_seq', 6, true);


--
-- PostgreSQL database dump complete
--


